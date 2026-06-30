import time
import random
from instagrapi import Client
from instagrapi.exceptions import ClientError


def _to_dict(users: list) -> dict:
    return {user.pk: user for user in users}


def fetch_followers(client: Client, user_id: int, progress_callback=None) -> dict:
    result = {}
    max_id = ""

    try:
        while True:
            batch, max_id = client.user_followers_v1_chunk(
                str(user_id), max_amount=0, max_id=max_id
            )
            result.update(_to_dict(batch))

            if progress_callback:
                progress_callback(len(result))

            if not max_id:
                break

            time.sleep(random.uniform(1.0, 2.0))
    except ClientError as e:
        raise RuntimeError(f"Failed to fetch followers: {e}")

    return result


def fetch_following(client: Client, user_id: int, progress_callback=None) -> dict:
    result = {}
    max_id = ""

    try:
        while True:
            batch, max_id = client.user_following_v1_chunk(
                str(user_id), max_amount=0, max_id=max_id
            )
            result.update(_to_dict(batch))

            if progress_callback:
                progress_callback(len(result))

            if not max_id:
                break

            time.sleep(random.uniform(1.0, 2.0))
    except ClientError as e:
        raise RuntimeError(f"Failed to fetch following: {e}")

    return result
