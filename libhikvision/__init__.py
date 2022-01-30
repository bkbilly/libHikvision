#!/usr/bin/python3

""" Import library like this: from libhikvision import libHikvision """
name = "libhikvision"

from struct import unpack
from datetime import datetime
from pytz import timezone
import os
import subprocess
import sqlite3


class libHikvision():
    """This library parses the Hikvision bin files and is able to extract the required media"""

    def __init__(self, cameradir, asktype='video'):
        """Inputs a cameradir where the datadirs and the info.bin exist.
           Can choose between a video or image."""
        self.cameradir = cameradir
        self.asktype = asktype

        self.header_len = 1280
        self.file_len = 32
        self.segment_len = 80
        self.maxSegments = 256
        self.video_len = 4096

        self.indexType = None
        self.segments = []
        self.get_index_path()
        self.info = self.getNASInfo()
        self.header = self.getFileHeader()

    def get_index_path(self, indexFileNum=0):
        self.indexType = 'bin'
        if self.asktype in ['video', 'mp4']:
            self.indexFile = 'index00.bin'
        elif self.asktype in ['image', 'img', 'pic']:
            self.indexFile = 'index00p.bin'
        filename = f"{self.cameradir}/datadir{indexFileNum}/{self.indexFile}"
        if not os.path.exists(filename):
            self.indexType = 'sqlite'
            self.indexFile = 'record_db_index00'
        filename = f"{self.cameradir}/datadir{indexFileNum}/{self.indexFile}"
        if not os.path.exists(filename):
            raise Exception("Can't find indexes...")
        return filename

    def getNASInfo(self):
        """Parses the info.bin file for some basic information."""
        nasinfo_len = 68
        info_keys = [
            'serialNumber',
            'MACAddr',
            'byRes',
            'f_bsize',
            'f_blocks',
            'DataDirs',
        ]
        fileName = f"{self.cameradir}/info.bin"
        unpackformat = "48s 4s B 3I".replace(' ', '')
        with open(fileName, mode='rb') as file:
            byte = file.read(nasinfo_len)
            info = dict(zip(info_keys, unpack(
                unpackformat, byte)))
        return info

    def getFileHeader(self):
        """Parses the index file of each datadir for some basic information"""
        header_keys = [
            'modifyTimes',
            'version',
            'avFiles',
            'nextFileRecNo',
            'lastFileRecNo',
            'curFileRec',
            'unknown',
            'checksum',
        ]
        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.get_index_path(indexFileNum)
            unpackformat = "Q 4I 1176s 76s I".replace(' ', '')
            with open(fileName, mode='rb') as file:
                byte = file.read(self.header_len)
                header = dict(zip(header_keys, unpack(
                    unpackformat, byte)))
        return header

    def getSegments(self, from_time=None, to_time=None, from_unixtime=None, to_unixtime=None):
        """Parses index file for information about each recording by 
           providing the exact path with the segment to extract.

        --== Parameters ==--
        Filters events based on the provided time provided in one of the following ways:
            Datetime: from_time & to_time eg. `datetime(2019, 8, 21, 22, 23, 30)`
            UnixTime: from_unixtime & to_unixtime eg. `1566415410`

        All the arguments default to None which means that it will return everythin.
        If only `from_*` is defined, then it will return from the provided time till now.
        If only `to_*` is defined, then it will return from the beginning till the provided time.
        If both are defined, then it will return all events withing this time period.

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
            WHERE record_type != 0 {limit_statement}
            ORDER BY start_time_tv_sec;'''

        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.get_index_path(indexFileNum)
            con = sqlite3.connect(fileName)
            cur = con.cursor()
            for fileNum, startOffset, endOffset, startTime, endTime in cur.execute(statement):
                segment = {}
                segment['startOffset'] = startOffset
                segment['endOffset'] = endOffset
                segment['cust_indexFileNum'] = indexFileNum
                segment['cust_startTime'] = datetime.utcfromtimestamp(startTime)
                segment['cust_endTime'] = datetime.utcfromtimestamp(endTime)
                segment['duration'] = endTime - startTime
                segment['cust_duration'] = endTime - startTime
                self.segments.append(segment)
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
        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.get_index_path(indexFileNum)
            unpackformat = "s s 2s 4s 3Q 4I 4s 4s 8s 4s 4s 4s 4s".replace(' ', '')
            offset = self.header_len + self.header['avFiles'] * self.file_len
            with open(fileName, mode='rb') as file:
                byte = file.read(offset)
                for fileNum in range(self.header['avFiles']):
                    for events in range(self.maxSegments):
                        byte = file.read(self.segment_len)
                        segment = dict(zip(segment_keys, unpack(
                            unpackformat, byte)))
                        segment['cust_fileNum'] = fileNum
                        segment['cust_indexFileNum'] = indexFileNum
                        segment['startTime'] = segment['startTime']
                        segment['endTime'] = segment['endTime']
                        segment['cust_startTime'] = datetime.utcfromtimestamp(segment['startTime']  & mask)
                        segment['cust_endTime'] = datetime.utcfromtimestamp(segment['endTime'] & mask)
                        segment['duration'] = segment['cust_endTime'] - segment['cust_startTime']
                        segment['cust_duration'] = segment['duration'].total_seconds()
                        fileExtension = 'mp4'
                        if 'p.bin' in self.indexFile:
                            fileExtension = 'pic'
                        segment['cust_filePath'] = '{0}datadir{1}/hiv{2:05d}.{3}'.format(self.cameradir, segment['cust_indexFileNum'], segment['cust_fileNum'], fileExtension)
                        if segment['endTime'] != 0:
                            # Filter segments by date
                            if from_time is None and to_time is None:
                                self.segments.append(segment)
                            elif from_time is not None and to_time is None:
                                if segment['cust_startTime'] > from_time:
                                    self.segments.append(segment)
                            elif from_time is None and to_time is not None:
                                if segment['cust_startTime'] < to_time:
                                    self.segments.append(segment)
                            elif from_time is not None and to_time is not None:
                                if segment['cust_startTime'] > from_time and segment['cust_startTime'] < to_time:
                                    self.segments.append(segment)

        # Sort by start time
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
            # Extracts the segment to a temporary h264 file
            #print('{0[cust_filePath]:55} {0[cust_duration]:5} {0[startOffset]:10} {0[endOffset]:10}   {0[cust_startTime]} - {0[cust_endTime]}'.format(
            #    self.segments[indx]
            #))
            with open(filePath, mode='rb') as video_in, open(h264_file, mode='wb') as video_out:
                video_in.seek(startOffset)
                while video_in.tell() < endOffset:
                    video_out.write(video_in.read(self.video_len))

            # Convert the h264 file to mp4
            if resolution is None:
                cmd = 'ffmpeg -i {0} -threads auto -c:v copy -c:a none {1} -hide_banner'.format(h264_file, mp4_file)
            else:
                cmd = 'avconv -i {0} -threads auto -s {2} -c:a none {1}'.format(h264_file, mp4_file, resolution)
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
        if not os.path.exists(jpg_file):
            #print('{0[cust_filePath]:55} {0[cust_duration]:5} {0[startOffset]:10} {0[endOffset]:10}   {0[cust_startTime]} - {0[cust_endTime]}'.format(
            #    self.segments[indx]
            #))
            with open(filePath, mode='rb') as video_in, open(h264_file, mode='wb') as video_out:
                video_in.seek(startOffset)
                while video_in.tell() < endOffset:
                    video_out.write(video_in.read(self.video_len))

            # Create JPG
            jpg_position = position
            if position is None:
                jpg_position = self.segments[indx]['cust_duration'] / 2
                if jpg_position >= 60:
                    jpg_position = 59
            if resolution is None:
                cmd = 'ffmpeg -ss 00:00:{2} -i {0} -hide_banner -vframes 1 {1}'.format(h264_file, jpg_file, jpg_position)
            else:
                cmd = 'ffmpeg -ss 00:00:{2} -i {0} -hide_banner -vframes 1 -s {3} {1}'.format(h264_file, jpg_file, jpg_position, resolution)

            if debug:
                subprocess.call(cmd, shell=True)
            else:
                subprocess.call(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.remove(h264_file)
        return jpg_file
