# LibHikvision
[![PyPI Version](https://img.shields.io/pypi/v/libHikvision?label=PyPI&logo=pypi)](https://pypi.org/project/libHikvision/)


Python library to parse Hikvision datadirs that Hikvision IP cameras store the videos.
Using this class you can view details about recordings stored in a datadir and extract video and thumbnails.


### Working Example

```python
#!/usr/bin/python3

from libhikvision import libHikvision
from datetime import datetime

cameradir = '/var/tmp/hikvision/'
hik = libHikvision(cameradir, 'video')

# Gets information about the structure of the files
for file in hik.getFiles():
    print(file)

# Get information about the server
print hik.getNASInfo()

# Extract the segments within a specific range of dates
segments = hik.getSegments(
    from_time=datetime(2019, 8, 21, 22, 23, 30),
    to_time=datetime(2019, 8, 21, 22, 25, 00),
)

# Extract the Videos and Images from segments found above
for num, segment in enumerate(segments, start=0):
    print('{0:4}) {1[cust_filePath]:55} {1[cust_duration]:5} {1[startOffset]:10} {1[endOffset]:10}   {1[cust_startTime]} - {1[cust_endTime]}'.format(
        num,
        segment
    ))

    print(hik.extractSegmentMP4(num, cachePath='/var/tmp/', filename='/var/tmp/video{0}.mp4'.format(num)))
    print(hik.extractSegmentJPG(num, cachePath='/var/tmp/', filename='/var/tmp/video{0}.jpg'.format(num)))
```

### Credits

Based on Dave Hope's PHP code available at https://github.com/davehope/libHikvision


