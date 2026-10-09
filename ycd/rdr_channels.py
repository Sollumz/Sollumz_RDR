"""Build supported RDR channels from sampled Blender animation values."""
import math
import struct
from ..cwxml import clipdictionary as xml


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def build_scalar_channel(values, indirect_percentage=0.1):
    values = [float32(v) for v in values]
    if not values or not all(math.isfinite(v) for v in values):
        raise ValueError('RDR animation channels require finite, nonempty samples.')
    unique = list(dict.fromkeys(values))
    if len(unique) == 1:
        channel = xml.ChannelsList.StaticFloat()
        channel.value = values[0]
        return channel
    offset = min(values)
    extent = max(values) - offset
    # Power-of-two quantum limits ordinary animation error while fitting 31 bits.
    magnitude = max(abs(v) for v in values)
    stable_exponent = math.floor(math.log2(magnitude)) - 21 if magnitude else -20
    quantum = float32(2.0 ** max(-20, stable_exponent,
                               math.ceil(math.log2(extent / ((1 << 30) - 1)))))
    quanta = [math.floor((v - offset) / quantum + 0.5) for v in values]
    try:
        decoded = [float32(float32(q * quantum) + offset) for q in quanta]
    except OverflowError:
        decoded = [math.inf] * len(values)
    if max(quanta) >= (1 << 31) or any(abs(a - b) > 2e-6 for a, b in zip(values, decoded)):
        channel = xml.ChannelsList.RawFloat()
        channel.values = values
        return channel
    if len(unique) / len(values) <= indirect_percentage:
        channel = xml.ChannelsList.IndirectQuantizeFloat()
        channel.values = unique
        indices = {v: i for i, v in enumerate(unique)}
        channel.frames = [indices[v] for v in values]
    else:
        acceleration = max((abs(quanta[i] - 2 * quanta[i - 1] + quanta[i - 2])
                            for i in range(2, len(quanta))), default=0)
        incremental = len(values) >= 64 and acceleration.bit_length() + 2 < max(quanta).bit_length()
        channel = (xml.ChannelsList.IncrementalFloat() if incremental
                   else xml.ChannelsList.QuantizeFloat())
        channel.values = values
    channel.quantum = quantum
    channel.offset = offset
    return channel


def build_quaternion_channels(quaternions):
    if not quaternions:
        raise ValueError('RDR quaternion channels require samples.')
    samples = []
    for q in quaternions:
        v = [float(q.x), float(q.y), float(q.z), float(q.w)]
        length = math.sqrt(sum(c * c for c in v))
        if not math.isfinite(length) or length == 0:
            raise ValueError('RDR animation contains an invalid quaternion.')
        samples.append([c / length for c in v])
    # The native type-7 marker reconstructs a positive omitted component. Choose
    # one whose sign is constant across the sequence; flip all samples together.
    candidates = [(min(abs(v[i]) for v in samples), i) for i in range(4)
                  if all(v[i] > 0 for v in samples) or all(v[i] < 0 for v in samples)]
    score, omitted = max(candidates, default=(0, 3))
    if score >= 0.25:
        sign = 1 if samples[0][omitted] > 0 else -1
        channels = [build_scalar_channel([v[i] * sign for v in samples])
                    for i in range(4) if i != omitted]
        marker = xml.ChannelsList.CachedQuaternion1()
        marker.quat_index = omitted
    else:
        channels = [build_scalar_channel([v[i] for v in samples]) for i in range(4)]
        marker = xml.ChannelsList.CachedQuaternion2()
        marker.quat_index = 0
    channels.append(marker)
    return channels
