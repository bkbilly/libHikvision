import setuptools

REQUIRES = [
    'pytz==2019.2',
]

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='libhikvision',  
    version='0.2',
    author="bkbilly",
    author_email="bkbilly@hotmail.com",
    description="Parse Hikvision datadirs that Hikvision IP cameras store the videos",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/bkbilly/libHikvision",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
 )
