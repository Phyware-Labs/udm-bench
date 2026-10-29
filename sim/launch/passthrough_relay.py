"""Passthrough relay for one TurtleBot3 sensor topic.

The burger SDF in the image is patched so Gazebo's sensor plugins publish
``<topic>_src``. One relay per topic in ``TB3_RELAY_TOPICS`` subscribes to that
remapped output and republishes it, unchanged, on the canonical ``<topic>`` that
Nav2 and the ``rosbag2`` recorder consume. The indirection is where the
benchmark's fault-injection relay sat when its faulted missions were recorded;
that relay is not part of this repository.

Run inside the TurtleBot3 container::

    python3 /opt/udm-bench/sim/launch/passthrough_relay.py --topic /scan
"""

from __future__ import annotations

import argparse
import importlib

#: Canonical topic -> (message module, class name).
TOPIC_TYPES: dict[str, tuple[str, str]] = {
    "/scan": ("sensor_msgs.msg", "LaserScan"),
    "/imu": ("sensor_msgs.msg", "Imu"),
}

SOURCE_SUFFIX = "_src"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="udm-bench passthrough relay")
    parser.add_argument("--topic", required=True, choices=sorted(TOPIC_TYPES))
    parser.add_argument("--qos-depth", type=int, default=10)
    args = parser.parse_args(argv)

    import rclpy
    from rclpy.node import Node

    module_name, class_name = TOPIC_TYPES[args.topic]
    msg_type = getattr(importlib.import_module(module_name), class_name)

    rclpy.init()
    node = Node(f"udm_bench_relay_{args.topic.strip('/').replace('/', '_')}")
    pub = node.create_publisher(msg_type, args.topic, args.qos_depth)
    node.create_subscription(msg_type, f"{args.topic}{SOURCE_SUFFIX}", pub.publish, args.qos_depth)
    node.get_logger().info(f"relay up: {args.topic}{SOURCE_SUFFIX} -> {args.topic}")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
