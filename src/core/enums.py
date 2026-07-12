from enum import IntEnum, IntFlag


class VKPoolFailedStatuses(IntEnum):
    EVENT_EXPIRED = 1
    KEY_EXPIRED = 2
    USER_DATA_EXPIRED = 3
    VERSION_UNKNOWN = 4


class VKPollEvents(IntEnum):
    NEW_MESSAGE_EVENT = 4


class VKPollFlags(IntFlag):
    UNREAD = 1
    OUTBOX = 2
    REPLIED = 4
    IMPORTANT = 8
    CHAT = 16
    FRIENDS = 32
    SPAM = 64
    DELETED = 128
    FIXED = 256
    MEDIA = 512
    HIDDEN = 65536
    DELETE_FOR_ALL = 64
    NOT_DELIVERED = 64
