import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'drone2'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        # Ament index
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        # Package manifest
        ('share/' + package_name, ['package.xml']),
        # Launch files
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
        # URDF / Xacro description
        (os.path.join('share', package_name, 'description'),
            glob(os.path.join('description', '*.xacro'))
            + glob(os.path.join('description', '*.urdf'))),
        # Gazebo world files
        (os.path.join('share', package_name, 'worlds'),
            glob(os.path.join('worlds', '*.world'))),
        # RViz config
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.rviz'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='onlydrones',
    maintainer_email='bobbyvinod100@gmail.com',
    description='Quadcopter simulation with ArduPilot SITL, Gazebo, and RViz2',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'gazebo_odom_bridge = drone2.gazebo_odom_bridge:main',
        ],
    },
)
