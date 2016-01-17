import click
import struct

from lxml import etree

from socket import (
    socket as Socket,
    AF_INET, SOCK_STREAM,
)

CHUNK_SIZE = 2048


def get_status(host):
    drobo_socket = Socket(
        AF_INET,
        SOCK_STREAM,
    )

    drobo_socket.connect((host, 5000))

    def read_bytes(message_length):
        chunks = []
        bytes_recd = 0
        while bytes_recd < message_length:
            chunk = drobo_socket.recv(min(message_length - bytes_recd, CHUNK_SIZE))
            if not chunk:
                raise RuntimeError("Could not read bytes")
            chunks.append(chunk)
            bytes_recd += len(chunk)
        return b''.join(chunks)

    initial_message = read_bytes(16)
    assert len(initial_message) == 16

    status_packet_length = struct.unpack('>i', initial_message[-4:])[0]
    status_message = read_bytes(status_packet_length)
    status_message = struct.unpack('{0}sx'.format(status_packet_length-1), status_message)
    status_message = status_message[0].strip()

    doc = etree.XML(status_message)
    return doc


CRITICAL = 2
WARNING = 1
OK = 0

TEXT_STATUSES = {
    CRITICAL: 'CRITICAL',
    WARNING: 'WARNING',
    OK: 'OK',
}


class DroboChecker:
    def __init__(self, host):
        self.status = get_status(host)

    def _get_threshold(self):
        def get_int(xpath):
            return int(self.status.xpath(xpath)[0].text)

        total_capacity = get_int('/ESATMUpdate/mTotalCapacityProtected')
        used_capacity = get_int('/ESATMUpdate/mUsedCapacityProtected')

        warning = get_int('/ESATMUpdate/mYellowThreshold') / 100
        critical = get_int('/ESATMUpdate/mRedThreshold') / 100

        return (used_capacity/total_capacity)*100, critical, warning

    def _get_failed_drives(self):
        slots_node = self.status.xpath('/ESATMUpdate/mSlotsExp')[0]
        for child_node in slots_node:
            if child_node.xpath('mStatus')[0].text != '3':
                slot_id = child_node.xpath('mSlotNumber')[0].text
                yield  slot_id + 1

    def check_capacity(self):
        pct_used, critical, warning = self._get_threshold()

        if pct_used > critical:
            cap_result = CRITICAL
        elif pct_used > warning:
            cap_result = WARNING
        else:
            cap_result = OK

        drive_result = OK
        failed_drives = []
        for failed_drive in self._get_failed_drives():
            drive_result = CRITICAL
            failed_drives.append(failed_drive)

        messages = [
            "%d%% of capacity used" % pct_used,
        ]
        for failed_drive in failed_drives:
            messages.append('drive #%s is not healthy' % failed_drive)

        result = max(cap_result, drive_result)
        result_text = TEXT_STATUSES[result]

        print("%s - %s" % (
            result_text, ', '.join(messages)
        ))
        exit(result)


@click.command()
@click.argument('host')
def main(host):
    checker = DroboChecker(host)

    checker.check_capacity()


if __name__ == '__main__':
    main()
