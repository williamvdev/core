"""Useful constants for unit tests."""
CONFIG = {
    "host": "localhost",
    "port": 58846,
    "username": "test-username",
    "password": "test-password",
}
CONNECTION_STATUS_RESPONSE_UPDOWN = {
    "download_rate": 512000,
    "dht_download_rate": 51200,
    "upload_rate": 81920,
    "dht_upload_rate": 8192,
}
CONNECTION_STATUS_RESPONSE_DOWNLOADING = {
    "download_rate": 512000,
    "dht_download_rate": 51200,
    "upload_rate": 0,
    "dht_upload_rate": 0,
}
CONNECTION_STATUS_RESPONSE_SEEDING = {
    "download_rate": 0,
    "dht_download_rate": 0,
    "upload_rate": 81920,
    "dht_upload_rate": 8192,
}
CONNECTION_STATUS_RESPONSE_IDLE = {
    "download_rate": 0,
    "dht_download_rate": 0,
    "upload_rate": 0,
    "dht_upload_rate": 0,
}

SESSION_STATE_SINGLE_TORRENT = ("64a980abe6e448226bb930ba061592e44c3781a1",)
SINGLE_TORRENT_STATUS_PAUSED = {
    "64a980abe6e448226bb930ba061592e44c3781a1": {"paused": True}
}
SINGLE_TORRENT_STATUS_ACTIVE = {
    "64a980abe6e448226bb930ba061592e44c3781a1": {"paused": False}
}
