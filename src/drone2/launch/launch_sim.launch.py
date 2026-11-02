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
      1. Robot State Publisher (Modular URDF with RPLIDAR A1 2D LiDAR)
      2. Gazebo Classic with ArduPilot plugin, RPLIDAR A1 sensor, and state publisher
      3. ArduPilot SITL (sim_vehicle.py) in an interactive terminal window
      4. Gazebo -> Odom bridge (publishes /drone2/odom + TF map->base_link + /drone2/path)
      5. RViz2 with odometry visualisation and /scan LaserScan display

    Usage:
      ros2 launch drone2 launch_sim.launch.py

    In the interactive ArduPilot SITL / MAVProxy console:
      mode guided
      arm throttle
      takeoff 5
      velocity 2 0 0
    """

    pkg_share = get_package_share_directory('drone2')

    use_sim_time = LaunchConfiguration('use_sim_time')
    use_xterm = LaunchConfiguration('use_xterm')

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

    # ── 1. Robot State Publisher ──
    rsp_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'rsp.launch.py')
        ),
        launch_arguments={'use_sim_time': use_sim_time}.items(),
    )

    # ── 2. Gazebo Classic ──
    world_file = os.path.join(pkg_share, 'worlds', 'drone2_ardupilot.world')

    # Gazebo models path
    pkg_models = os.path.join(pkg_share, 'models')
    ardupilot_gazebo_models = os.path.expanduser('~/ardupilot_gazebo/models')
    current_model_path = os.environ.get('GAZEBO_MODEL_PATH', '')
    gazebo_model_path = f"{pkg_models}:{ardupilot_gazebo_models}"
    if current_model_path:
        gazebo_model_path = f"{gazebo_model_path}:{current_model_path}"

    # Gazebo plugin path
    ardupilot_gazebo_build = os.path.expanduser('~/ardupilot_gazebo/build')
    current_plugin_path = os.environ.get('GAZEBO_PLUGIN_PATH', '')
    gazebo_plugin_path = ardupilot_gazebo_build
    if current_plugin_path:
        gazebo_plugin_path = ardupilot_gazebo_build + ':' + current_plugin_path

    gazebo_env = {
        'GAZEBO_MODEL_PATH': gazebo_model_path,
        'GAZEBO_PLUGIN_PATH': gazebo_plugin_path,
    }

    gazebo_server = ExecuteProcess(
        cmd=[
            'gazebo', '--verbose',
            '-s', 'libgazebo_ros_init.so',
            '-s', 'libgazebo_ros_factory.so',
            '-s', 'libgazebo_ros_state.so',
            world_file,
        ],
        output='screen',
        additional_env=gazebo_env,
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
        period=5.0,
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
        period=5.0,
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
            Node(
                package='rviz2',
                executable='rviz2',
                name='rviz2',
                output='screen',
                arguments=['-d', rviz_config],
                parameters=[{'use_sim_time': use_sim_time}],
            )
        ],
    )

    return LaunchDescription([
        declare_use_sim_time,
        declare_use_xterm,
        rsp_launch,
        gazebo_server,
        ardupilot_sitl_xterm,
        ardupilot_sitl_direct,
        odom_bridge_node,
        rviz_node,
    ])
