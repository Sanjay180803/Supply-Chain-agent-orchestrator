"""
Create the request topic with one partition per orchestrator replica.

Kafka auto-creates topics with a single partition by default, and a
consumer group can use at most one consumer per partition, so with the
auto-created topic only one orchestrator replica ever receives work.

    KAFKA_BOOTSTRAP=localhost:9092 python create_topic.py --partitions 3
"""
import argparse
import os

from kafka.admin import KafkaAdminClient, NewPartitions, NewTopic
from kafka.errors import TopicAlreadyExistsError

TOPIC = "supply-chain-requests"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--partitions", type=int, default=3)
    args = parser.parse_args()

    admin = KafkaAdminClient(bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "localhost:9092"))
    try:
        admin.create_topics([NewTopic(TOPIC, num_partitions=args.partitions, replication_factor=1)])
        print(f"Created {TOPIC} with {args.partitions} partitions")
    except TopicAlreadyExistsError:
        current = len(admin.describe_topics([TOPIC])[0]["partitions"])
        if current < args.partitions:
            admin.create_partitions({TOPIC: NewPartitions(total_count=args.partitions)})
            print(f"Increased {TOPIC} from {current} to {args.partitions} partitions")
        else:
            print(f"{TOPIC} already has {current} partitions")
    finally:
        admin.close()


if __name__ == "__main__":
    main()
