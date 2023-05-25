# -*- coding: utf-8 -*-
"""
tests for unsolicited response logic
"""


from oobabot import decide_to_respond


def test_last_reply_times():
    # a unit test which stores 10 timestamps, then purges the oldest 5
    # and checks that the remaining 5 are the newest 5
    lrt = decide_to_respond.LastReplyTimes(10, 5)
    for i in range(10):
        lrt[i] = i
    lrt.purge_outdated(10)
    assert len(lrt) == 5
    assert sorted(lrt.values()) == [5, 6, 7, 8, 9]


def test_values_purged_when_cache_timeout_happens():
    # a unit test which stores 10 timestamps, but with a timeout
    # of 4 seconds.  Checks that after 5 seconds, there are 9
    # timestamps left, and that the oldest one is 1 second old.
    lrt = decide_to_respond.LastReplyTimes(4, 0)
    for i in range(10):
        lrt[i] = i
    lrt.purge_outdated(5)
    assert len(lrt) == 9
    assert sorted(lrt.values())[0] == 1

    lrt.purge_outdated(13)
    assert len(lrt) == 1
    assert sorted(lrt.values())[0] == 9

    lrt.purge_outdated(14)
    assert len(lrt) == 0


def test_when_not_full():
    # a unit test which stores 5 timestamps with an unsolicited
    # channel cap of 10, and checks that they're all there
    lrt = decide_to_respond.LastReplyTimes(10, 10)
    for i in range(5):
        lrt[i] = i
    lrt.purge_outdated(5)
    assert len(lrt) == 5
    assert sorted(lrt.values()) == [0, 1, 2, 3, 4]


def test_unlimited_channels():
    # a unit test which stores 5 timestamps with an unsolicited
    # channel cap of 0, and checks that they're all there
    lrt = decide_to_respond.LastReplyTimes(5, 0)
    for i in range(5):
        lrt[i] = i
    lrt.purge_outdated(5)
    assert len(lrt) == 5
    assert sorted(lrt.values()) == [0, 1, 2, 3, 4]


def test_when_empty():
    # test that when the cache is empty, we don't crash
    lrt = decide_to_respond.LastReplyTimes(10, 10)
    lrt.purge_outdated(5)
    assert len(lrt) == 0
