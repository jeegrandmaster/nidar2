import os
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    ExecuteProcess,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    """
    Launch the full drone2 simulation stack:
      1. Robot State Publisher and custom Xacro robot description
      2. Gazebo Classic with the custom robot, IMU, ArduPilot plugin, and state publisher
      3. ArduPilot SITL (sim_vehicle.py) in an interactive terminal window
      4. Gazebo -> Odom bridge (publishes /drone2/odom + TF map->base_link + /drone2/path)
      5. RViz2 with odometry visualisation

    Usage:
      ros2 launch drone2 launch_sim.launch.py

    In the interactive ArduPilot SITL / MAVProxy console:
      # Indoor attitude-only takeoff (no GPS):
      mode stabilize
      arm throttle
      rc 3 1700
    """

    pkg_share = get_package_share_directory('drone2')

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_xterm = LaunchConfiguration('use_xterm')
    use_rviz = LaunchConfiguration('use_rviz')

    # ── Declare launch arguments ──
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation (Gazebo) clock if true',
    )

    declare_use_xterm = DeclareLaunchArgument(
        'use_xterm',
        default_value='true',
        description='Launch SITL MAVProxy console in a dedicated xterm window for interactive commands',
    )

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz2 visualization if true',
    )

    # ── 1. Robot State Publisher ──
    rsp_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'rsp.launch.py')
        ),
        launch_arguments={'use_sim_time': use_sim_time}.items(),
    )

    # ── 2. Gazebo Classic ──
    world_file = os.path.join(pkg_share, 'worlds', 'drone2_ardupilot.world')

    # Gazebo plugin path
    ardupilot_gazebo_build = os.path.expanduser('~/ardupilot_gazebo/build')
    current_plugin_path = os.environ.get('GAZEBO_PLUGIN_PATH', '')
    gazebo_plugin_path = ardupilot_gazebo_build
    if current_plugin_path:
        gazebo_plugin_path = ardupilot_gazebo_build + ':' + current_plugin_path

    gazebo_env = {
        'GAZEBO_PLUGIN_PATH': gazebo_plugin_path,
    }
    gui_env = {
        **gazebo_env,
        'QT_QPA_PLATFORM': 'xcb',
        'GDK_BACKEND': 'x11',
    }
    gui_env_command = [
        'env',
        '-u', 'SNAP',
        '-u', 'SNAP_LIBRARY_PATH',
        '-u', 'GTK_PATH',
        '-u', 'GTK_EXE_PREFIX',
    ]

    gazebo_server = ExecuteProcess(
        cmd=[
            'gzserver', '--verbose',
            '-s', 'libgazebo_ros_init.so',
            '-s', 'libgazebo_ros_factory.so',
            world_file,
        ],
        output='screen',
        additional_env=gazebo_env,
    )

    gazebo_client = TimerAction(
        period=2.0,
        actions=[
            ExecuteProcess(
                cmd=gui_env_command + ['gzclient'],
                output='screen',
                additional_env=gui_env,
            )
        ],
    )

    # Spawn the custom robot_description, not a Gazebo model/SDF.
    spawn_robot = TimerAction(
        period=3.0,
        actions=[
            Node(
                package='gazebo_ros',
                executable='spawn_entity.py',
                arguments=[
                    '-topic', 'robot_description',
                    '-entity', 'drone2',
                    '-z', '0.25',
                ],
                output='screen',
            )
        ],
    )

    # ── 3. ArduPilot SITL ──
    # Starts sim_vehicle.py after a delay to let Gazebo finish launching
    sitl_script = os.path.expanduser('~/ardupilot/Tools/autotest/sim_vehicle.py')
    sitl_base_cmd = [
        sitl_script,
        '-v', 'ArduCopter',
        '-f', 'gazebo-iris',
        '--console',
        '-I', '0',
    ]

    # With xterm (default): opens interactive terminal window where you can type commands directly
    ardupilot_sitl_xterm = TimerAction(
        period=8.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    'xterm',
                    '-T', 'ArduPilot SITL - MAVProxy Console',
                    '-geometry', '110x35+50+50',
                    '-hold',
                    '-e',
                ] + sitl_base_cmd,
                output='screen',
                cwd=os.path.expanduser('~/ardupilot/ArduCopter'),
                condition=IfCondition(use_xterm),
            )
        ],
    )

    # Without xterm: runs directly
    ardupilot_sitl_direct = TimerAction(
        period=8.0,
        actions=[
            ExecuteProcess(
                cmd=sitl_base_cmd,
                output='screen',
                cwd=os.path.expanduser('~/ardupilot/ArduCopter'),
                condition=UnlessCondition(use_xterm),
            )
        ],
    )

    # ── 4. Gazebo → Odometry Bridge ──
    # Reads /gazebo/model_states, publishes /drone2/odom and TF (map→base_link) + /drone2/path
    odom_bridge_node = TimerAction(
        period=3.0,
        actions=[
            Node(
                package='drone2',
                executable='gazebo_odom_bridge',
                name='gazebo_odom_bridge',
                output='screen',
                parameters=[{
                    'model_name': 'drone2',
                    'odom_frame': 'map',
                    'base_frame': 'base_link',
                    'publish_tf': True,
                    'use_sim_time': use_sim_time,
                }],
            )
        ],
    )

    # ── 5. RViz2 ──
    rviz_config = os.path.join(pkg_share, 'config', 'drone2.rviz')

    rviz_node = TimerAction(
        period=3.0,
        actions=[
            ExecuteProcess(
                cmd=gui_env_command + [
                    'rviz2',
                    '-d', rviz_config,
                    '--ros-args',
                    '-r', '__node:=rviz2',
                ],
                output='screen',
                additional_env=gui_env,
                condition=IfCondition(use_rviz),
            )
        ],
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_use_xterm,
        declare_use_rviz,
        rsp_launch,
        gazebo_server,
        gazebo_client,
        spawn_robot,
        ardupilot_sitl_xterm,
        ardupilot_sitl_direct,
        odom_bridge_node,
        rviz_node,
    ])
