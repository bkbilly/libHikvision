import struct
from datetime import datetime
import os

cameradir = '/home/bkbilly/Desktop/hikvision/'

info_keys = [
    'serialNumber',
    'MACAddr',
    'byRes',
    'f_bsize',
    'f_blocks',
    'DataDirs',
]
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

nasinfo_len = 68
header_len = 1280
file_len = 32
segment_len = 80
maxSegments = 256
mask = 0x00000000ffffffff


# getNASInfo
fileName = cameradir + 'info.bin'
unpackformat = "48s 4s B 3I".replace(' ', '')
with open(fileName, mode='rb') as file:
    byte = file.read(nasinfo_len)
    info = dict(zip(info_keys, struct.unpack(
        unpackformat, byte)))


# getFileHeaderForIndexFile
segments = []
for indexFile in range(info['DataDirs']):
    fileName = cameradir + 'datadir%s/index00.bin' % (indexFile)
    if not os.path.exists(fileName):
        print('Path not found: ' + fileName)
    else:
        unpackformat = "Q 4I 1176s 76s I".replace(' ', '')
        with open(fileName, mode='rb') as file:
            byte = file.read(header_len)
            header = dict(zip(header_keys, struct.unpack(
                unpackformat, byte)))

        # getFilesForIndexFile (Not Used)
        unpackformat = "I 2H 2I s s H 4s 8s".replace(' ', '')
        offset = header_len
        with open(fileName, mode='rb') as file:
            byte = file.read(offset)
            for i in range(header['avFiles']):
                byte = file.read(file_len)
                files = dict(zip(files_keys, struct.unpack(
                    unpackformat, byte)))
                if files['chan'] != 65535:
                    # print(struct.unpack(unpackformat, byte))
                    print(files)

        # getSegmentsForIndexFile
        unpackformat = "s s 2s 4s 3Q 4I 4s 4s 8s 4s 4s 4s 4s".replace(' ', '')
        offset = header_len + header['avFiles'] * file_len
        with open(fileName, mode='rb') as file:
            byte = file.read(offset)
            for fileNum in range(header['avFiles']):
                for events in range(maxSegments):
                    byte = file.read(segment_len)
                    segment = dict(zip(segment_keys, struct.unpack(
                        unpackformat, byte)))
                    segment['cust_fileNum'] = fileNum
                    segment['cust_indexFileNum'] = indexFile
                    segment['cust_startTime'] = datetime.fromtimestamp(segment['startTime'] & mask)
                    segment['cust_endTime'] = datetime.fromtimestamp(segment['endTime'] & mask)
                    segment['duration'] = segment['cust_endTime'] - segment['cust_startTime']
                    segment['cust_duration'] = segment['duration'].total_seconds()
                    segment['cust_filePath'] = '{0}datadir{1}/hiv{2:05d}.mp4'.format(cameradir, segment['cust_indexFileNum'], segment['cust_fileNum'])
                    fileName = cameradir + 'datadir%s/index00.bin' % (indexFile)
                    if segment['endTime'] != 0:
                        segments.append(segment)

segments.sort(key=lambda item:item['cust_startTime'], reverse=False)

for segment in segments:
    print(
        segment['cust_filePath'],
        segment['cust_duration'],
        segment['startOffset'],
        segment['endOffset'],
        segment['cust_startTime'],
        segment['cust_endTime'],
    )
print len(segments)
