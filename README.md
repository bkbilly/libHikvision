# README #

Python library to parse Hikvision datadirs that Hikvision IP cameras store the videos.
Using this class you can view details about recordings stored in a datadir and extract video and thumbnails.


### Working Example ###

```python
#!/usr/bin/python3

from libhikvision import libHikvision
from datetime import datetime

cameradir = '/var/tmp/hikvision/'
hik = libHikvision(cameradir, 'video')
segments = hik.getSegments(
    from_time=datetime(2019, 8, 21, 22, 23, 30),
    to_time=datetime(2019, 8, 21, 22, 25, 00),
)

# Gets information about the structure of the files
for file in hik.getFiles():
    print(file)

# Extract the Videos and Images from segments found above
for num, segment in enumerate(segments, start=0):
    print('{0:4}) {1[cust_filePath]:55} {1[cust_duration]:5} {1[startOffset]:10} {1[endOffset]:10}   {1[cust_startTime]} - {1[cust_endTime]}'.format(
        num,
        segment
    ))

    print(hik.extractSegmentMP4(num, '/var/tmp/'))
    print(hik.extractSegmentJPG(num, '/var/tmp/'))
```

### Credits ###

Based on Dave Hope's PHP code available at https://github.com/davehope/libHikvision


