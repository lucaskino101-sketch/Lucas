import numpy as np

from ictmodel.structures import fvgs, resample_ohlc, swing_points


def naive_swings(h, l, n):
    sh = np.zeros(len(h), bool)
    sl = np.zeros(len(h), bool)
    for k in range(n, len(h) - n):
        sh[k] = h[k] > h[k - n:k].max() and h[k] >= h[k + 1:k + n + 1].max()
        sl[k] = l[k] < l[k - n:k].min() and l[k] <= l[k + 1:k + n + 1].min()
    return sh, sl


def test_swings_match_naive_definition():
    rng = np.random.default_rng(0)
    c = np.cumsum(rng.normal(size=500))
    h, l = c + rng.random(500), c - rng.random(500)
    for n in (1, 2, 3):
        got, want = swing_points(h, l, n), naive_swings(h, l, n)
        assert (got[0] == want[0]).all() and (got[1] == want[1]).all()


def test_fvg_definition():
    #            0     1     2     3     4
    h = np.array([10., 12., 15., 14., 9.])
    l = np.array([9., 10., 11., 12., 8.])
    bull, bear = fvgs(h, l)
    assert bull[2]            # low[2]=11 > high[0]=10
    assert not bull[3]        # low[3]=12 > high[1]=12 is false
    assert bear[4]            # high[4]=9 < low[2]=11
    assert not bull[0] and not bull[1]


def test_resample_buckets():
    o = np.arange(6.0)
    h = o + 1
    l = o - 1
    c = o + 0.5
    ids, ho, hh, hl, hc, last = resample_ohlc(o, h, l, c, np.array([0, 0, 0, 1, 1, 1]))
    assert list(ids) == [0, 1]
    assert list(ho) == [0, 3] and list(hh) == [3, 6] and list(hl) == [-1, 2] and list(hc) == [2.5, 5.5]
    assert list(last) == [2, 5]
