#!/usr/bin/python3

""" Command Line Interface for libHikvision """

import argparse
import json
import os
import sys
from datetime import datetime
from libhikvision import libHikvision


def parse_time_arg(val):
    if not val:
        return None
    val = val.strip()
    if val.isdigit():
        return datetime.fromtimestamp(int(val))
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"Invalid datetime format: '{val}'. Use 'YYYY-MM-DD HH:MM:SS' or unix timestamp."
    )


def parse_indices(val, max_count):
    if val.lower() == 'all':
        return list(range(max_count))
    indices = []
    for part in val.split(','):
        part = part.strip()
        if '-' in part:
            start_str, end_str = part.split('-', 1)
            start, end = int(start_str), int(end_str)
            indices.extend(range(start, end + 1))
        else:
            indices.append(int(part))
    return [i for i in indices if 0 <= i < max_count]


def main(args=None):
    parser = argparse.ArgumentParser(
        prog="libhikvision",
        description="CLI tool to parse Hikvision IP Camera and DVR storage archives and extract video/thumbnails."
    )
    parser.add_argument(
        "target",
        metavar="PATH",
        help="Directory or index file (.bin / record_db_index00) to parse"
    )
    parser.add_argument(
        "-t", "--type",
        choices=["video", "image", "mp4", "pic"],
        default="video",
        help="Media type to look for (default: video)"
    )
    parser.add_argument(
        "-c", "--channel",
        type=int,
        default=None,
        help="Channel number filter for multi-channel DVRs"
    )
    parser.add_argument(
        "--from",
        dest="from_time",
        type=parse_time_arg,
        default=None,
        help="Start datetime (e.g. '2026-07-16 18:00:00' or timestamp)"
    )
    parser.add_argument(
        "--to",
        dest="to_time",
        type=parse_time_arg,
        default=None,
        help="End datetime (e.g. '2026-07-16 22:00:00' or timestamp)"
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all matching segments (default action)"
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Print NAS / DVR storage information"
    )
    parser.add_argument(
        "--header",
        action="store_true",
        help="Print index file header details"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output information in JSON format"
    )
    parser.add_argument(
        "--extract-mp4",
        metavar="INDICES",
        help="Extract MP4 video for segment indices (e.g. '0', '0,1,2', '0-5', 'all')"
    )
    parser.add_argument(
        "--extract-jpg",
        metavar="INDICES",
        help="Extract JPG thumbnail for segment indices (e.g. '0', '0,1,2', '0-5', 'all')"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="./extracted",
        help="Destination folder for extracted media (default: ./extracted)"
    )
    parser.add_argument(
        "-r", "--resolution",
        default=None,
        help="Resolution for extracted video/image (e.g. '1280x720')"
    )
    parser.add_argument(
        "--num-files",
        type=int,
        default=None,
        help="Override number of chunk files in circular buffer (e.g. 4 or 35 for HIKBTREE)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable ffmpeg debugging output"
    )
    parser.add_argument(
        "--no-replace",
        dest="replace",
        action="store_false",
        default=True,
        help="Do not overwrite existing output files"
    )

    parsed = parser.parse_args(args)

    if not os.path.exists(parsed.target):
        print(f"Error: Path '{parsed.target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        hik = libHikvision(parsed.target, parsed.type, num_files=parsed.num_files)
    except Exception as e:
        print(f"Error initializing libHikvision: {e}", file=sys.stderr)
        sys.exit(1)

    if parsed.info:
        if parsed.json:
            info_dict = {
                k: v.decode('latin1', errors='ignore') if isinstance(v, bytes) else v
                for k, v in hik.info.items()
            }
            print(json.dumps(info_dict, indent=2))
        else:
            print("=== NAS / Storage Information ===")
            for k, v in hik.info.items():
                if isinstance(v, bytes):
                    val_str = v.rstrip(b'\x00').decode('latin1', errors='ignore') if len(v) <= 64 else v.hex()
                elif isinstance(v, list):
                    val_str = ", ".join(str(x) for x in v)
                else:
                    val_str = str(v)
                print(f"  {k}: {val_str}")
        if not (parsed.header or parsed.list or parsed.extract_mp4 or parsed.extract_jpg):
            return

    if parsed.header:
        if parsed.json:
            header_dict = {
                k: v.hex() if isinstance(v, bytes) and len(v) > 32 else (v.decode('latin1', errors='ignore') if isinstance(v, bytes) else v)
                for k, v in hik.header.items()
            }
            print(json.dumps(header_dict, indent=2))
        else:
            print("=== Index File Header ===")
            for k, v in hik.header.items():
                if isinstance(v, bytes):
                    val_str = f"<{len(v)} bytes hex: {v[:16].hex()}...>" if len(v) > 32 else v.rstrip(b'\x00').decode('latin1', errors='ignore')
                elif isinstance(v, list):
                    val_str = ", ".join(str(x) for x in v)
                else:
                    val_str = str(v)
                print(f"  {k}: {val_str}")
        if not (parsed.list or parsed.extract_mp4 or parsed.extract_jpg):
            return

    segments = hik.getSegments(
        from_time=parsed.from_time,
        to_time=parsed.to_time,
        channel=parsed.channel
    )

    if parsed.extract_mp4 is not None or parsed.extract_jpg is not None:
        os.makedirs(parsed.output_dir, exist_ok=True)
        if parsed.extract_mp4 is not None:
            indices = parse_indices(parsed.extract_mp4, len(segments))
            if not indices:
                print(f"No valid segments matching index '{parsed.extract_mp4}'. Total segments found: {len(segments)}")
            for idx in indices:
                seg = segments[idx]
                if seg.get('overwritten'):
                    print(f"Warning: Segment #{idx} ({seg['cust_startTime']}) was overwritten on disk by newer recordings (Chunk #{seg.get('raw_file_idx')} is older than active retention window). Extracted video will likely be incomplete or empty.", file=sys.stderr)
                dt_str = seg['cust_startTime'].strftime('%Y%m%d_%H%M%S')
                ch_str = f"_ch{seg['channel']}" if 'channel' in seg else ""
                out_file = os.path.join(parsed.output_dir, f"video_{dt_str}{ch_str}_seg{idx:04d}.mp4")
                print(f"Extracting MP4 segment #{idx} ({seg['cust_startTime']} -> {seg['cust_endTime']}) to {out_file}...")
                hik.extractSegmentMP4(
                    idx,
                    cachePath=parsed.output_dir,
                    filename=out_file,
                    resolution=parsed.resolution,
                    debug=parsed.debug,
                    replace=parsed.replace
                )
                print(f"Saved: {out_file}")

        if parsed.extract_jpg is not None:
            indices = parse_indices(parsed.extract_jpg, len(segments))
            if not indices:
                print(f"No valid segments matching index '{parsed.extract_jpg}'. Total segments found: {len(segments)}")
            for idx in indices:
                seg = segments[idx]
                if seg.get('overwritten'):
                    print(f"Warning: Segment #{idx} ({seg['cust_startTime']}) was overwritten on disk by newer recordings (Chunk #{seg.get('raw_file_idx')} is older than active retention window).", file=sys.stderr)
                dt_str = seg['cust_startTime'].strftime('%Y%m%d_%H%M%S')
                ch_str = f"_ch{seg['channel']}" if 'channel' in seg else ""
                out_file = os.path.join(parsed.output_dir, f"thumb_{dt_str}{ch_str}_seg{idx:04d}.jpg")
                print(f"Extracting JPG thumbnail for segment #{idx} ({seg['cust_startTime']}) to {out_file}...")
                hik.extractSegmentJPG(
                    idx,
                    cachePath=parsed.output_dir,
                    filename=out_file,
                    resolution=parsed.resolution,
                    debug=parsed.debug,
                    replace=parsed.replace
                )
                print(f"Saved: {out_file}")
        return

    try:
        # Default action: list segments
        if parsed.json:
            json_segs = []
            for i, s in enumerate(segments):
                item = dict(s)
                item['index'] = i
                item['cust_startTime'] = s['cust_startTime'].isoformat()
                item['cust_endTime'] = s['cust_endTime'].isoformat()
                item['duration_seconds'] = s['cust_duration']
                if 'duration' in item and hasattr(item['duration'], 'total_seconds'):
                    item['duration'] = item['duration'].total_seconds()
                json_segs.append(item)
            print(json.dumps(json_segs, indent=2))
        else:
            print(f"Found {len(segments)} segment(s) [Format: {hik.indexType}]:")
            for num, segment in enumerate(segments):
                ch_info = f"Ch {segment['channel']:2d} | " if 'channel' in segment else ""
                chunk_info = f" (Chunk #{segment['raw_file_idx']})" if 'raw_file_idx' in segment and segment.get('raw_file_idx') != segment.get('cust_fileNum') else ""
                overwritten_tag = " [OVERWRITTEN]" if segment.get('overwritten') else ""
                dur_str = f"{segment['cust_duration']:6.1f}s" if isinstance(segment['cust_duration'], float) else f"{segment['cust_duration']:5d}s"
                print(f"[{num:4d}] {ch_info}{segment['cust_filePath']}{chunk_info} | {segment['cust_startTime']} -> {segment['cust_endTime']} ({dur_str}){overwritten_tag}")
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
