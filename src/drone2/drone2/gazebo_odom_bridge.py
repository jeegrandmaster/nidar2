"""
Gazebo Model State → Odometry Bridge for drone2.

Subscribes to /gazebo/model_states (from gazebo_ros), finds the drone model,
and publishes nav_msgs/Odometry + tf2 transforms so RViz can visualize
the drone's position and orientation in real-time.

This replaces the need for MAVROS for odometry visualization.
When MAVROS is installed later, you can switch to /mavros/local_position/odom.
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
    """Bridge Gazebo model states to ROS 2 odometry."""

    def __init__(self):
        super().__init__('gazebo_odom_bridge')

        # Parameters
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

        # Subscribe to Gazebo model states
        qos = QoSProfile(
            depth=10,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )
        self.sub = self.create_subscription(
            ModelStates,
            '/gazebo/model_states',
            self.model_states_cb,
            qos,
        )

        self.get_logger().info(
            f'Gazebo Odom Bridge started — tracking model "{self.model_name}"'
        )

    def model_states_cb(self, msg: ModelStates):
        # Find our model
        try:
            idx = msg.name.index(self.model_name)
        except ValueError:
            # Try alternate names (the model might be nested)
            for i, name in enumerate(msg.name):
                if self.model_name in name or 'iris' in name.lower():
                    idx = i
                    break
            else:
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

        # Publish TF: map → base_link
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

        # Accumulate path
        ps = PoseStamped()
        ps.header.stamp = now
        ps.header.frame_id = self.odom_frame
        ps.pose = pose
        self.path_msg.poses.append(ps)

        # Limit path length to avoid memory bloat
        if len(self.path_msg.poses) > 5000:
            self.path_msg.poses = self.path_msg.poses[-2500:]

        self.path_msg.header.stamp = now
        self.path_pub.publish(self.path_msg)


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
