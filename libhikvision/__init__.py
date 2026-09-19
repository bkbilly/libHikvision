#!/usr/bin/python3

""" Import library like this: from libhikvision import libHikvision """

from struct import unpack
from datetime import datetime
from pytz import timezone
import os
import subprocess
import sqlite3

name = "libhikvision"

class libHikvision():
    """This library parses the Hikvision bin files and is able to extract the required media"""

    def __init__(self, cameradir, asktype='video'):
        """Inputs a cameradir where the datadirs and the info.bin exist,
           or an explicit path to an index file (.bin / record_db_index00).
           Can choose between a video or image."""
        if os.path.isfile(cameradir):
            self.indexFilePath = os.path.abspath(cameradir)
            self.cameradir = os.path.dirname(self.indexFilePath)
            self.indexFile = os.path.basename(self.indexFilePath)
        else:
            self.indexFilePath = None
            self.cameradir = cameradir
            self.indexFile = None
        self.asktype = asktype

        self.header_len = 1280
        self.file_len = 32
        self.segment_len = 80
        self.video_len = 4096
        self.indexType = None
        self.segments = []
        self.get_index_path()
        self.info = self.getNASInfo()
        self.header = self.getFileHeader()
        if 'p.bin' in (self.indexFile or '').lower() or self.asktype in ['image', 'img', 'pic']:
            self.maxSegments = 4096
        else:
            self.maxSegments = 256

    def _find_file_ci(self, dir_path, filename):
        if not os.path.exists(dir_path):
            return None
        target_lower = filename.lower()
        for entry in os.listdir(dir_path):
            if entry.lower() == target_lower:
                return os.path.join(dir_path, entry)
        return None

    def get_index_path(self, indexFileNum=0):
        if self.indexFilePath and os.path.isfile(self.indexFilePath):
            filename = self.indexFilePath
        else:
            if self.asktype in ['video', 'mp4']:
                self.indexFile = 'index00.bin'
            elif self.asktype in ['image', 'img', 'pic']:
                self.indexFile = 'index00p.bin'

            search_dirs = [
                f"{self.cameradir}/datadir{indexFileNum}",
                self.cameradir,
            ]

            filename = None
            for d in search_dirs:
                f_path = self._find_file_ci(d, self.indexFile)
                if f_path:
                    filename = f_path
                    break

            if filename is None:
                self.indexFile = 'record_db_index00'
                for d in search_dirs:
                    f_path = self._find_file_ci(d, self.indexFile)
                    if f_path:
                        filename = f_path
                        break

        if filename is None or not os.path.exists(filename):
            raise Exception("Can't find indexes...")

        # Detect index type from file contents
        with open(filename, mode='rb') as f:
            header_sample = f.read(64)
            if b'HIKBTREE' in header_sample:
                self.indexType = 'hikbtree'
            elif header_sample.startswith(b'SQLite format 3'):
                self.indexType = 'sqlite'
            elif self.indexFile and 'record_db_index00' in self.indexFile.lower():
                self.indexType = 'sqlite'
            else:
                self.indexType = 'bin'

        return filename

    def getNASInfo(self):
        """Parses the info.bin file for some basic information."""
        nasinfo_len = 68
        fileName = f"{self.cameradir}/info.bin"
        if not os.path.exists(fileName):
            datadirs = [
                d for d in os.listdir(self.cameradir)
                if os.path.isdir(os.path.join(self.cameradir, d)) and d.startswith('datadir')
            ]
            num_datadirs = len(datadirs) if len(datadirs) > 0 else 1
            if self.indexFilePath:
                num_datadirs = 1
            return {
                'serialNumber': '',
                'MACAddr': '',
                'byRes': 0,
                'f_bsize': 4096,
                'f_blocks': 0,
                'DataDirs': num_datadirs,
            }
        with open(fileName, mode='rb') as file:
            byte = file.read(nasinfo_len)
            sn_raw, mac_raw, res, f_bsize, f_blocks, data_dirs = unpack('<48s6s2s3I', byte)
            info = {
                'serialNumber': sn_raw.rstrip(b'\x00').decode('latin1', errors='ignore'),
                'MACAddr': ':'.join(f'{b:02X}' for b in mac_raw),
                'byRes': int.from_bytes(res, 'little'),
                'f_bsize': f_bsize,
                'f_blocks': f_blocks,
                'DataDirs': data_dirs,
            }
        return info

    def getFileHeader(self):
        """Parses the index file of each datadir for some basic information"""
        if self.indexType == 'hikbtree':
            for indexFileNum in range(self.info['DataDirs']):
                fileName = self.get_index_path(indexFileNum)
                with open(fileName, mode='rb') as file:
                    byte = file.read(128)
                    magic = byte[16:24].rstrip(b'\x00').decode('latin1', errors='ignore')
                    version = byte[32:48].rstrip(b'\x00').decode('latin1', errors='ignore')
                    pageSize = unpack('<I', byte[52:56])[0]
                    treeDepth = unpack('<I', byte[56:60])[0]
                    ts = unpack('<I', byte[60:64])[0]
                    totalItems = unpack('<I', byte[104:108])[0]
                    header = {
                        'format': 'hikbtree',
                        'magic': magic,
                        'version': version,
                        'pageSize': pageSize,
                        'treeDepth': treeDepth,
                        'timestamp': ts,
                        'totalItems': totalItems,
                    }
            return header
        elif self.indexType == 'sqlite':
            fileName = self.get_index_path(0)
            header = {
                'format': 'sqlite',
                'version': 1,
                'totalFiles': 0,
                'totalSegments': 0,
                'validSegments': 0,
                'tables': [],
            }
            try:
                con = sqlite3.connect(fileName)
                cur = con.cursor()
                tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
                header['tables'] = tables

                for v_tbl in ['record_db_version_tb', 'event_db_version_tb']:
                    if v_tbl in tables:
                        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({v_tbl})").fetchall()]
                        if cols:
                            row = cur.execute(f"SELECT {cols[0]} FROM {v_tbl} LIMIT 1").fetchone()
                            if row:
                                header['version'] = row[0]
                        break

                total_files = 0
                total_segments = 0
                valid_segments = 0
                for indexFileNum in range(self.info['DataDirs']):
                    d_file = self.get_index_path(indexFileNum)
                    d_con = sqlite3.connect(d_file)
                    d_cur = d_con.cursor()
                    for f_tbl in ['record_file_idx_tb', 'event_file_idx_tb']:
                        if f_tbl in tables:
                            total_files += d_cur.execute(f"SELECT count(*) FROM {f_tbl}").fetchone()[0]
                            break
                    for s_tbl in ['record_segment_idx_tb', 'event_segment_idx_tb']:
                        if s_tbl in tables:
                            total_segments += d_cur.execute(f"SELECT count(*) FROM {s_tbl}").fetchone()[0]
                            valid_segments += d_cur.execute(f"SELECT count(*) FROM {s_tbl} WHERE record_type != 0 AND end_time_tv_sec > start_time_tv_sec").fetchone()[0]
                            break
                    d_con.close()

                header['totalFiles'] = total_files
                header['totalSegments'] = total_segments
                header['validSegments'] = valid_segments
                con.close()
            except Exception as e:
                header['error'] = str(e)
            return header
        else:
            for indexFileNum in range(self.info['DataDirs']):
                fileName = self.get_index_path(indexFileNum)
                unpackformat = "Q 4I 1176s 76s I".replace(' ', '')
                with open(fileName, mode='rb') as file:
                    byte = file.read(self.header_len)
                    modifyTimes, version, avFiles, nextFileRecNo, lastFileRecNo, cur_bytes, unk_bytes, checksum = unpack(
                        unpackformat, byte
                    )
                    active_channels = []
                    for i in range(49):
                        slot = cur_bytes[i * 24 : (i + 1) * 24]
                        chan, file_no, seg_count = unpack('<HHI', slot[:8])
                        if chan != 0xFFFF:
                            active_channels.append({
                                'channel': chan,
                                'fileNo': file_no,
                                'segments': seg_count,
                            })

                    header = {
                        'format': 'bin',
                        'version': version,
                        'avFiles': avFiles,
                        'nextFileRecNo': nextFileRecNo,
                        'lastFileRecNo': lastFileRecNo,
                        'modifyTimes': modifyTimes,
                        'activeChannels': active_channels,
                        'checksum': checksum,
                    }
            return header

    def getSegments(self, from_time=None, to_time=None, from_unixtime=None, to_unixtime=None, channel=None):
        """Parses index file for information about each recording by 
           providing the exact path with the segment to extract.

        --== Parameters ==--
        Filters events based on the provided time provided in one of the following ways:
            Datetime: from_time & to_time eg. `datetime(2019, 8, 21, 22, 23, 30)`
            UnixTime: from_unixtime & to_unixtime eg. `1566415410`
            Channel:  channel eg. `8` (for DVR / HIKBTREE multi-channel recordings)

        All the arguments default to None which means that it will return everything.
        If only `from_*` is defined, then it will return from the provided time till now.
        If only `to_*` is defined, then it will return from the beginning till the provided time.
        If both are defined, then it will return all events within this time period.

        --== Returns ==--
        Returns a list of dictionaries with each event. The most important is the index of this
        dictionary which can be used to extract the video or image.
        """
        if from_unixtime is not None:
            from_time = datetime.fromtimestamp(from_unixtime)
        if to_unixtime is not None:
            to_time = datetime.fromtimestamp(to_unixtime)
        if from_time is not None:
            from_unixtime = int(datetime.timestamp(from_time))
        if to_time is not None:
            to_unixtime = int(datetime.timestamp(to_time))

        if self.indexType == 'bin':
            self.getSegmentsBIN(from_time, to_time)
        elif self.indexType == 'sqlite':
            self.getSegmentsSQL(from_unixtime, to_unixtime)
        elif self.indexType == 'hikbtree':
            self.getSegmentsHIKBTREE(from_time, to_time, channel=channel)
        return self.segments

    def getSegmentsSQL(self, from_unixtime=None, to_unixtime=None):
        limit_statement = ""
        if from_unixtime is not None:
            limit_statement += f" AND start_time_tv_sec >= {from_unixtime}"
        if to_unixtime is not None:
            limit_statement += f" AND start_time_tv_sec <= {to_unixtime}"
        self.segments = []
        statement = f'''SELECT
                file_no as "cust_fileNum",
                start_offset as "startOffset",
                end_offset as "endOffset",
                start_time_tv_sec as "startTime",
                end_time_tv_sec as "endTime"
            FROM record_segment_idx_tb
            WHERE record_type != 0 AND end_time_tv_sec > start_time_tv_sec {limit_statement}
            ORDER BY start_time_tv_sec;'''

        fileExtension = 'mp4'
        if 'p.bin' in (self.indexFile or '').lower():
            fileExtension = 'pic'

        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.get_index_path(indexFileNum)
            search_dir = os.path.dirname(fileName)
            con = sqlite3.connect(fileName)
            cur = con.cursor()
            for fileNum, startOffset, endOffset, startTime, endTime in cur.execute(statement):
                file_path = os.path.join(search_dir, f'hiv{fileNum:05d}.{fileExtension}')
                segment = {}
                segment['cust_fileNum'] = fileNum
                segment['startOffset'] = startOffset
                segment['endOffset'] = endOffset
                segment['cust_indexFileNum'] = indexFileNum
                segment['startTime'] = startTime
                segment['endTime'] = endTime
                segment['cust_startTime'] = datetime.fromtimestamp(startTime)
                segment['cust_endTime'] = datetime.fromtimestamp(endTime)
                segment['duration'] = datetime.fromtimestamp(endTime) - datetime.fromtimestamp(startTime)
                segment['cust_duration'] = endTime - startTime
                segment['cust_filePath'] = file_path
                self.segments.append(segment)

        # Sort by start time across all datadirs
        self.segments.sort(key=lambda item: item['cust_startTime'], reverse=False)
        return self.segments

    def getSegmentsBIN(self, from_time=None, to_time=None):
        self.segments = []

        mask = 0x00000000ffffffff
        segment_keys = [
            'type',
            'status',
            'resA',
            'resolution',
            'startTime',
            'endTime',
            'firstKeyFrame_absTime',
            'firstKeyFrame_stdTime',
            'lastFrame_stdTime',
            'startOffset',
            'endOffset',
            'resB',
            'infoNum',
            'infoTypes',
            'infoStartTime',
            'infoEndTime',
            'infoStartOffset',
            'infoEndOffset',
        ]
        max_segments = 4096 if ('p.bin' in (self.indexFile or '').lower() or self.asktype in ['image', 'img', 'pic']) else 256
        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.get_index_path(indexFileNum)
            search_dir = os.path.dirname(fileName)
            unpackformat = "s s 2s 4s 3Q 4I 4s 4s 8s 4s 4s 4s 4s".replace(' ', '')
            offset = self.header_len + self.header['avFiles'] * self.file_len
            with open(fileName, mode='rb') as file:
                byte = file.read(offset)
                for fileNum in range(self.header['avFiles']):
                    for events in range(max_segments):
                        byte = file.read(self.segment_len)
                        if len(byte) < self.segment_len:
                            break
                        segment = dict(zip(segment_keys, unpack(
                            unpackformat, byte)))
                        segment['cust_fileNum'] = fileNum
                        segment['cust_indexFileNum'] = indexFileNum
                        segment['startTime'] = segment['startTime']
                        segment['endTime'] = segment['endTime']
                        segment['cust_startTime'] = datetime.fromtimestamp(segment['startTime'] & mask)
                        segment['cust_endTime'] = datetime.fromtimestamp(segment['endTime'] & mask)
                        segment['duration'] = segment['cust_endTime'] - segment['cust_startTime']
                        segment['cust_duration'] = segment['duration'].total_seconds()
                        fileExtension = 'mp4'
                        if 'p.bin' in (self.indexFile or '').lower() or self.asktype in ['image', 'img', 'pic']:
                            fileExtension = 'pic'
                        if self.indexFilePath:
                            segment['cust_filePath'] = os.path.join(self.cameradir, f'hiv{segment["cust_fileNum"]:05d}.{fileExtension}')
                        else:
                            segment['cust_filePath'] = os.path.join(search_dir, f'hiv{segment["cust_fileNum"]:05d}.{fileExtension}')
                        if segment['endTime'] != 0:
                            # Filter segments by date
                            if from_time is None and to_time is None:
                                self.segments.append(segment)
                            elif from_time is not None and to_time is None:
                                if segment['cust_startTime'] >= from_time:
                                    self.segments.append(segment)
                            elif from_time is None and to_time is not None:
                                if segment['cust_startTime'] <= to_time:
                                    self.segments.append(segment)
                            elif from_time is not None and to_time is not None:
                                if segment['cust_startTime'] >= from_time and segment['cust_startTime'] <= to_time:
                                    self.segments.append(segment)

        # Sort by start time
        self.segments.sort(key=lambda item: item['cust_startTime'], reverse=False)
        return self.segments

    def getSegmentsHIKBTREE(self, from_time=None, to_time=None, channel=None):
        self.segments = []
        fileExtension = 'mp4'
        if 'p.bin' in self.indexFile.lower():
            fileExtension = 'pic'

        page_size = 4096
        base_offset = 0x04c5e000
        file_size = 1073741824

        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.get_index_path(indexFileNum)
            search_dir = os.path.dirname(fileName)
            hiv_files = sorted([
                f for f in os.listdir(search_dir)
                if f.startswith('hiv') and f.endswith(f'.{fileExtension}')
            ])
            num_files = len(hiv_files) if len(hiv_files) > 0 else 1

            with open(fileName, mode='rb') as file:
                data = file.read()

            total_pages = len(data) // page_size
            for p in range(total_pages):
                page = data[p * page_size : (p + 1) * page_size]
                if len(page) < 4:
                    continue
                ptype = unpack('<I', page[:4])[0]
                if ptype != 2:
                    continue

                rec_count = unpack('<I', page[16:20])[0]
                if rec_count > 80:
                    rec_count = (page_size - 96) // 48

                for i in range(rec_count):
                    off = 96 + i * 48
                    rec = page[off : off + 48]
                    if len(rec) < 48:
                        break

                    t1, t2 = unpack('<2I', rec[24:32])
                    if not (1000000000 < t1 < 2147483647 and 1000000000 < t2 < 2147483647):
                        continue
                    if t1 == t2:
                        continue

                    ch = rec[17]
                    rec_type = rec[19]

                    if channel is not None and ch != channel:
                        continue

                    disk_offset = unpack('<Q', rec[32:40])[0]
                    raw_file_idx = (disk_offset - base_offset) // file_size
                    file_num = raw_file_idx % num_files if num_files > 0 else raw_file_idx

                    file_path = os.path.join(search_dir, f'hiv{file_num:05d}.{fileExtension}')

                    segment = {
                        'channel': ch,
                        'record_type': rec_type,
                        'startTime': t1,
                        'endTime': t2,
                        'cust_fileNum': file_num,
                        'cust_indexFileNum': indexFileNum,
                        'cust_startTime': datetime.fromtimestamp(t1),
                        'cust_endTime': datetime.fromtimestamp(t2),
                        'duration': datetime.fromtimestamp(t2) - datetime.fromtimestamp(t1),
                        'cust_duration': t2 - t1,
                        'cust_filePath': file_path,
                        'startOffset': 0,
                        'endOffset': file_size,
                        'diskOffset': disk_offset,
                    }

                    if from_time is None and to_time is None:
                        self.segments.append(segment)
                    elif from_time is not None and to_time is None:
                        if segment['cust_startTime'] >= from_time:
                            self.segments.append(segment)
                    elif from_time is None and to_time is not None:
                        if segment['cust_startTime'] <= to_time:
                            self.segments.append(segment)
                    elif from_time is not None and to_time is not None:
                        if segment['cust_startTime'] >= from_time and segment['cust_startTime'] <= to_time:
                            self.segments.append(segment)

        self.segments.sort(key=lambda item: item['cust_startTime'], reverse=False)
        return self.segments

    def extractSegmentMP4(self, indx, cachePath='/var/tmp', filename=None, resolution=None, debug=False, replace=True):
        """Extracts the segment to an MP4 file in the provided directory

        --== Parameters ==--
        indx:       The index that corresponds to the getSegments command.
        cachePath:  Folder to save temporary files for the conversion. The default is `/var/tmp`.
        filename:   Defines the path with the name for the output file.
                    If `None` then saves it to the cachePath directory with a default name.
        resolution: Changes to specific resolution. It should be in the format `Width x Height` eg. `480x270`.
                    If `None` then it mentains the orignal resolution which is preferable because it is faster.
        debug:      Shows the output of the shell command.
        replace:    If True then removes the file with the same name if it exists and creates it.
                    If False it checks if the file exists and doesn't let it create it again.

        --== Returns ==--
        Returns the output file path.
        """
        filePath = self.segments[indx]['cust_filePath']
        startOffset = self.segments[indx]['startOffset']
        endOffset = self.segments[indx]['endOffset']
        h264_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.h264'.format(cachePath, self.segments[indx])
        if filename is None:
            mp4_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.mp4'.format(cachePath, self.segments[indx])
        else:
            mp4_file = filename

        if os.path.exists(mp4_file) and replace:
            os.remove(mp4_file)
        if not os.path.exists(mp4_file) or replace:
            with open(filePath, mode='rb') as video_in, open(h264_file, mode='wb') as video_out:
                video_in.seek(startOffset)
                while video_in.tell() < endOffset:
                    chunk_size = min(self.video_len, endOffset - video_in.tell())
                    chunk = video_in.read(chunk_size)
                    if not chunk:
                        break
                    video_out.write(chunk)

            # Convert the h264 file to mp4
            if resolution is None:
                cmd = 'ffmpeg -i {0} -threads auto -c:v copy -an {1} -hide_banner'.format(h264_file, mp4_file)
            else:
                cmd = 'avconv -i {0} -threads auto -s {2} -an {1}'.format(h264_file, mp4_file, resolution)
            if debug:
                subprocess.call(cmd, shell=True)
            else:
                subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.remove(h264_file)
        return mp4_file

    def extractSegmentJPG(self, indx, cachePath='/var/tmp', filename=None, resolution=None, debug=False, replace=True, position=None):
        """Extracts an thumbnail to the provided directory

        --== Parameters ==--
        indx:       The index that corresponds to the getSegments command.
        cachePath:  Folder to save temporary files for the conversion. The default is `/var/tmp`.
        filename:   Defines the path with the name for the output file.
                    If `None` then saves it to the cachePath directory with a default name.
        resolution: Changes to specific resolution. It should be in the format `Width x Height` eg. `480x270`.
                    If `None` then it mentains the orignal resolution which is preferable because it is faster.
        debug:      Shows the output of the shell command.
        replace:    If True then removes the file with the same name if it exists and creates it.
                    If False it checks if the file exists and doesn't let it create it again.
        position:   It should be an integer which correspond to seconds from the start of the video on which
                    an image is extracted. If `None` then it finds it automatically arround the middle and not
                    beyond 1 minute.

        --== Returns ==--
        Returns the output file path.
        """
        filePath = self.segments[indx]['cust_filePath']
        startOffset = self.segments[indx]['startOffset']
        endOffset = self.segments[indx]['endOffset']
        h264_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.h264'.format(cachePath, self.segments[indx])
        if filename is None:
            jpg_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.jpg'.format(cachePath, self.segments[indx])
        else:
            jpg_file = filename

        if os.path.exists(jpg_file) and replace:
            os.remove(jpg_file)
        if not os.path.exists(jpg_file) or replace:
            if filePath.endswith('.pic') or 'p.bin' in (self.indexFile or '').lower() or self.asktype in ['image', 'img', 'pic']:
                with open(filePath, mode='rb') as pic_in:
                    pic_in.seek(startOffset)
                    pic_bytes = pic_in.read(endOffset - startOffset)
                soi = pic_bytes.find(b'\xff\xd8')
                if soi != -1:
                    eoi = pic_bytes.rfind(b'\xff\xd9')
                    if eoi != -1:
                        pic_bytes = pic_bytes[soi : eoi + 2]
                    else:
                        pic_bytes = pic_bytes[soi:]
                with open(jpg_file, mode='wb') as pic_out:
                    pic_out.write(pic_bytes)

                if resolution is not None:
                    tmp_scaled = jpg_file + '.tmp.jpg'
                    cmd = f'ffmpeg -y -i "{jpg_file}" -s {resolution} "{tmp_scaled}" -hide_banner'
                    if debug:
                        subprocess.call(cmd, shell=True)
                    else:
                        subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if os.path.exists(tmp_scaled):
                        os.replace(tmp_scaled, jpg_file)
                return jpg_file

            with open(filePath, mode='rb') as video_in, open(h264_file, mode='wb') as video_out:
                video_in.seek(startOffset)
                while video_in.tell() < endOffset:
                    chunk_size = min(self.video_len, endOffset - video_in.tell())
                    chunk = video_in.read(chunk_size)
                    if not chunk:
                        break
                    video_out.write(chunk)

            # Create JPG
            jpg_position = position
            if position is None:
                jpg_position = self.segments[indx]['cust_duration'] / 2
                if jpg_position >= 60:
                    jpg_position = 59
            if resolution is None:
                cmd = 'ffmpeg -ss 00:00:{2} -i {0} -hide_banner -vframes 1 {1}'.format(h264_file, jpg_file, int(jpg_position))
            else:
                cmd = 'ffmpeg -ss 00:00:{2} -i {0} -hide_banner -vframes 1 -s {3} {1}'.format(h264_file, jpg_file, int(jpg_position), resolution)

            if debug:
                subprocess.call(cmd, shell=True)
            else:
                subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.remove(h264_file)
        return jpg_file
