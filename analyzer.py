def find_non_followers(following: dict, followers: dict) -> list:
    following_ids = set(following.keys())
    followers_ids = set(followers.keys())
    non_follower_ids = following_ids - followers_ids

    result = []
    for uid in non_follower_ids:
        user = following[uid]
        result.append({
            "pk": uid,
            "username": user.username,
            "full_name": user.full_name or "",
        })

    result.sort(key=lambda x: x["username"].lower())
    return result
