"""
Gazebo Model State -> Odometry & TF Bridge for drone2.

Subscribes to /gazebo/model_states (published by libgazebo_ros_state.so),
tracks the 'drone2' model, and publishes:
  - /drone2/odom (nav_msgs/Odometry)
  - /drone2/path (nav_msgs/Path)
  - TF transform: map -> base_link
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSDurabilityPolicy, QoSReliabilityPolicy

from gazebo_msgs.msg import ModelStates
from nav_msgs.msg import Odometry, Path
from geometry_msgs.msg import (
    PoseStamped,
    TransformStamped,
)
from tf2_ros import TransformBroadcaster


class GazeboOdomBridge(Node):
    """Bridge Gazebo model states to ROS 2 odometry and TF."""

    def __init__(self):
        super().__init__('gazebo_odom_bridge')

        # Declare parameters
        self.declare_parameter('model_name', 'drone2')
        self.declare_parameter('odom_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('publish_tf', True)

        self.model_name = self.get_parameter('model_name').value
        self.odom_frame = self.get_parameter('odom_frame').value
        self.base_frame = self.get_parameter('base_frame').value
        self.publish_tf = self.get_parameter('publish_tf').value

        # Publishers
        self.odom_pub = self.create_publisher(Odometry, '/drone2/odom', 10)
        self.path_pub = self.create_publisher(Path, '/drone2/path', 10)

        # TF broadcaster
        self.tf_broadcaster = TransformBroadcaster(self)

        # Path accumulator
        self.path_msg = Path()
        self.path_msg.header.frame_id = self.odom_frame

        # Subscribe to /gazebo/model_states
        # Use a flexible QoS profile compatible with gazebo_ros_state
        qos = QoSProfile(depth=10)
        self.sub = self.create_subscription(
            ModelStates,
            '/gazebo/model_states',
            self.model_states_cb,
            qos,
        )

        self.get_logger().info(
            f'Gazebo Odom Bridge initialized — tracking model "{self.model_name}"'
        )

    def model_states_cb(self, msg: ModelStates):
        # Locate the model in the states list
        idx = -1
        try:
            idx = msg.name.index(self.model_name)
        except ValueError:
            # Fallback search if model name is prefixed or namespaced
            for i, name in enumerate(msg.name):
                if self.model_name.lower() in name.lower() or 'iris' in name.lower():
                    idx = i
                    break
            else:
                self.get_logger().warn(
                    f'Model "{self.model_name}" not found in /gazebo/model_states: {msg.name}',
                    throttle_duration_sec=5.0
                )
                return

        pose = msg.pose[idx]
        twist = msg.twist[idx]
        now = self.get_clock().now().to_msg()

        # Publish Odometry
        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        odom.pose.pose = pose
        odom.twist.twist = twist
        self.odom_pub.publish(odom)

        # Broadcast TF: map -> base_link
        if self.publish_tf:
            t = TransformStamped()
            t.header.stamp = now
            t.header.frame_id = self.odom_frame
            t.child_frame_id = self.base_frame
            t.transform.translation.x = pose.position.x
            t.transform.translation.y = pose.position.y
            t.transform.translation.z = pose.position.z
            t.transform.rotation = pose.orientation
            self.tf_broadcaster.sendTransform(t)

        # Append to Path
        ps = PoseStamped()
        ps.header.stamp = now
        ps.header.frame_id = self.odom_frame
        ps.pose = pose
        self.path_msg.poses.append(ps)

        # Limit path points to prevent excessive memory usage
        if len(self.path_msg.poses) > 5000:
            self.path_msg.poses = self.path_msg.poses[-2500:]

        self.path_msg.header.stamp = now
        self.path_pub.publish(self.path_msg)

        # Informative periodic log
        self.get_logger().info(
            f'Tracking [{msg.name[idx]}] pose: x={pose.position.x:.2f}, y={pose.position.y:.2f}, z={pose.position.z:.2f}',
            throttle_duration_sec=3.0
        )


def main(args=None):
    rclpy.init(args=args)
    node = GazeboOdomBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
