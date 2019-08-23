from struct import unpack
from datetime import datetime
import os

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

    def extractSegmentMP4(self, filePath, cachePath, startOffset, endOffset, resolution=None):
        with open(filePath, mode='rb') as video_in, open(cachePath, mode='wb') as video_out:
            video_in.seek(startOffset)
            while video_in.tell() < endOffset:
                video_out.write(video_in.read(self.video_len))


cameradir = '/home/bkbilly/Desktop/hikvision/'
hik = libHikvision(cameradir, 'video')
segments = hik.getSegments()

for segment in segments:
    print(
        segment['cust_filePath'],
        segment['cust_duration'],
        segment['startOffset'],
        segment['endOffset'],
        segment['cust_startTime'],
        segment['cust_endTime'],
    )
print(len(segments))

hik.extractSegmentMP4('/home/bkbilly/Desktop/hikvision/datadir0/hiv00034.mp4', '/home/bkbilly/Desktop/test.mp4', 30572544, 81727120)
# for file in hik.getFiles():
#     print(file)