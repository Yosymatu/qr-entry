import tomllib

from pyinstaller_versionfile import create_versionfile_from_distribution


with open('pyproject.toml', 'rb') as f:
    pyproject_data = tomllib.load(f)


version_info: dict[str, str | list[int]] = pyproject_data.get('tool', {}).get('pyinstaller-versionfile', {})
    

create_versionfile_from_distribution(
    output_file='QRGateApp.version',
    distname='QRGateApp',
    **version_info
)