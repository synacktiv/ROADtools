from setuptools import setup
setup(name='roadrecon',
      version='2.0.0',
      description='Entra ID (Azure AD) recon for red and blue',
      author='Dirk-jan Mollema',
      author_email='dirkjan@dirkjanm.io',
      url='https://github.com/dirkjanm/ROADtools/',
      license='MIT',
      classifiers=[
          'Intended Audience :: Information Technology',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.10',
          'Programming Language :: Python :: 3.11',
          'Programming Language :: Python :: 3.12',
          'Programming Language :: Python :: 3.13',
          'Programming Language :: Python :: 3.14',
      ],
      packages=[
        'roadtools.roadrecon',
        'roadtools.roadrecon.plugins',
        'roadtools.roadrecon.api',
        'roadtools.roadrecon.api.routers',
        'roadtools.roadrecon.dist_gui',
        'roadtools.roadrecon.dist_gui.assets'
      ],
      package_data={
        'roadtools.roadrecon.plugins': ['*.yaml'],
        'roadtools.roadrecon.dist_gui': ['*'],
        'roadtools.roadrecon.dist_gui.assets': ['*'],
      },
      install_requires=[
          'roadlib>=1.7',
          'sqlalchemy>=2',
          'fastapi>=0.115',
          'uvicorn',
          'aiohttp',
          'openpyxl'
      ],
      extras_require={
          'road2timeline': ['pyyaml', 'numpy', 'pandas']
      },
      zip_safe=False,
      include_package_data=True,
      entry_points={
          'console_scripts': ['roadrecon-gui=roadtools.roadrecon.api.__main__:main',
                              'roadrecon=roadtools.roadrecon.main:main']
      }
      )
