#!/usr/bin/python3

from struct import unpack
from datetime import datetime
import os
import subprocess

class libHikvision():
    """docstring for libHikvision"""
    def __init__(self, cameradir, asktype='video'):
        self.cameradir = cameradir
        if asktype in ['video', 'mp4']:
            self.indexFile = 'index00.bin'
        elif asktype in ['image', 'img', 'pic']:
            self.indexFile = 'index00p.bin'
        
        self.nasinfo_len = 68
        self.header_len = 1280
        self.file_len = 32
        self.segment_len = 80
        self.maxSegments = 256
        self.video_len = 4096

        self.info = {}
        self.header = {}
        self.files = []
        self.segments = []


    def getNASInfo(self):
        info_keys = [
            'serialNumber',
            'MACAddr',
            'byRes',
            'f_bsize',
            'f_blocks',
            'DataDirs',
        ]
        fileName = self.cameradir + 'info.bin'
        unpackformat = "48s 4s B 3I".replace(' ', '')
        with open(fileName, mode='rb') as file:
            byte = file.read(self.nasinfo_len)
            self.info = dict(zip(info_keys, unpack(
                unpackformat, byte)))
        self.checkPaths()
        return self.info

    def checkPaths(self):
        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.cameradir + 'datadir%s/%s' % (indexFileNum, self.indexFile)
            if not os.path.exists(fileName):
                print('Path not found: ' + fileName)

    def getFileHeaderForIndexFile(self):
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
        self.segments = []
        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.cameradir + 'datadir%s/%s' % (indexFileNum, self.indexFile)
            unpackformat = "Q 4I 1176s 76s I".replace(' ', '')
            with open(fileName, mode='rb') as file:
                byte = file.read(self.header_len)
                self.header = dict(zip(header_keys, unpack(
                    unpackformat, byte)))
        return self.header

    def getFilesForIndexFile(self):
        files_keys = [
            'fileNo',
            'chan',
            'segRecNums',
            'startTime',
            'endTime',
            'status',
            'unknownA',
            'lockedSegNum',
            'unknownB',
            'infoTypes',
        ]
        for indexFileNum in range(self.info['DataDirs']):
            fileName = self.cameradir + 'datadir%s/%s' % (indexFileNum, self.indexFile)
            unpackformat = "I 2H 2I s s H 4s 8s".replace(' ', '')
            offset = self.header_len
            with open(fileName, mode='rb') as file:
                byte = file.read(offset)
                for i in range(self.header['avFiles']):
                    byte = file.read(self.file_len)
                    myfile = dict(zip(files_keys, unpack(
                        unpackformat, byte)))
                    if myfile['chan'] != 65535:
                        self.files.append(myfile)
        return self.files

    def getSegmentsForIndexFile(self):
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
            fileName = self.cameradir + 'datadir%s/%s' % (indexFileNum, self.indexFile)
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
                        segment['cust_startTime'] = datetime.fromtimestamp(segment['startTime'] & mask)
                        segment['cust_endTime'] = datetime.fromtimestamp(segment['endTime'] & mask)
                        segment['duration'] = segment['cust_endTime'] - segment['cust_startTime']
                        segment['cust_duration'] = segment['duration'].total_seconds()
                        fileExtension = 'mp4'
                        if 'p.bin' in self.indexFile:
                            fileExtension = 'pic'
                        segment['cust_filePath'] = '{0}datadir{1}/hiv{2:05d}.{3}'.format(self.cameradir, segment['cust_indexFileNum'], segment['cust_fileNum'], fileExtension)
                        fileName = self.cameradir + 'datadir%s/%s.bin' % (indexFileNum, self.indexFile)
                        if segment['endTime'] != 0:
                            self.segments.append(segment)

        self.segments.sort(key=lambda item:item['cust_startTime'], reverse=False)
        return self.segments

    def getSegments(self):
        self.getNASInfo()
        self.getFileHeaderForIndexFile()
        return self.getSegmentsForIndexFile()

    def getFiles(self):
        self.getNASInfo()
        self.getFileHeaderForIndexFile()
        return self.getFilesForIndexFile()

    def extractSegmentMP4(self, indx, cachePath, resolution=None):
        filePath = self.segments[indx]['cust_filePath']
        startOffset = self.segments[indx]['startOffset']
        endOffset = self.segments[indx]['endOffset']
        h264_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.h264'.format(cachePath, self.segments[indx])
        mp4_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.mp4'.format(cachePath, self.segments[indx])
        jpg_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.jpg'.format(cachePath, self.segments[indx])
        if not os.path.exists(mp4_file):
            print('{0[cust_filePath]:55} {0[cust_duration]:5} {0[startOffset]:10} {0[endOffset]:10}   {0[cust_startTime]} - {0[cust_endTime]}'.format(
                self.segments[indx]
            ))
            with open(filePath, mode='rb') as video_in, open(h264_file, mode='wb') as video_out:
                video_in.seek(startOffset)
                while video_in.tell() < endOffset:
                    video_out.write(video_in.read(self.video_len))

            # Create MP4
            if resolution is None:
                cmd = 'ffmpeg -i {0} -threads auto -c:v copy -c:a none {1} -hide_banner'.format(h264_file, mp4_file)
            else:
                cmd = 'avconv -i {0} -threads auto -s {2} -c:a none {1}'.format(h264, mp4_file, resolution)
            subprocess.call(cmd, shell=True)
            os.remove(h264_file)

    def extractSegmentJPG(self, indx, cachePath, resolution='480x270'):
        filePath = self.segments[indx]['cust_filePath']
        startOffset = self.segments[indx]['startOffset']
        endOffset = self.segments[indx]['endOffset']
        h264_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.h264'.format(cachePath, self.segments[indx])
        jpg_file = '{0}/hik_datadir{1[cust_indexFileNum]}_{1[startOffset]}_{1[endOffset]}.jpg'.format(cachePath, self.segments[indx])
        if not os.path.exists(jpg_file):
            print('{0[cust_filePath]:55} {0[cust_duration]:5} {0[startOffset]:10} {0[endOffset]:10}   {0[cust_startTime]} - {0[cust_endTime]}'.format(
                self.segments[indx]
            ))
            with open(filePath, mode='rb') as video_in, open(h264_file, mode='wb') as video_out:
                video_in.seek(startOffset)
                while video_in.tell() < endOffset:
                    video_out.write(video_in.read(self.video_len))

            # Create JPG
            jpg_position = self.segments[indx]['cust_duration'] / 2
            if jpg_position >= 60:
                jpg_position = 59
            cmd = 'ffmpeg -ss 00:00:{2} -i {0} -hide_banner -vframes 1 -s {3} {1}'.format(h264_file, jpg_file, jpg_position, resolution)
            subprocess.call(cmd, shell=True)
            os.remove(h264_file)



cameradir = '/home/bkbilly/Desktop/hikvision/'
hik = libHikvision(cameradir, 'video')
segments = hik.getSegments()

for num, segment in enumerate(segments, start=0):
    print('{0:4}) {1[cust_filePath]:55} {1[cust_duration]:5} {1[startOffset]:10} {1[endOffset]:10}   {1[cust_startTime]} - {1[cust_endTime]}'.format(
        num,
        segment
    ))

hik.extractSegmentMP4(379, '/home/bkbilly/Desktop/')
hik.extractSegmentJPG(379, '/home/bkbilly/Desktop/')
# for file in hik.getFiles():
#     print(file)