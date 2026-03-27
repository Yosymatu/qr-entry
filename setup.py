from setuptools import setup, find_packages


with open(file='requirements.txt', mode='r', encoding='utf-8') as require_file:
    requires = require_file.read().splitlines()


with open(file='VERSION.txt', mode='r', encoding='utf-8') as vf:
    version = vf.read().strip()


setup(
    name='QRGateApp',
    version=version,
    description='QR code reader',
    packages=find_packages(exclude=['data']),
    include_package_data=True,
    requires=requires
)