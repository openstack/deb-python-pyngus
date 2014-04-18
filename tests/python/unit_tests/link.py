#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
import common
# import logging

from proton import Condition
from proton import Message

import dingus


class APITest(common.Test):

    def setup(self, props=None):
        # logging.getLogger("dingus").setLevel(logging.DEBUG)
        self.container1 = dingus.Container("test-container-1")
        self.conn1_handler = common.ConnCallback()
        if props is None:
            # props = {"x-trace-protocol": True}
            props = {"x-trace-protocol": False}
        self.conn1 = self.container1.create_connection("conn1",
                                                       self.conn1_handler,
                                                       props)
        self.conn1.open()

        self.container2 = dingus.Container("test-container-2")
        self.conn2_handler = common.ConnCallback()
        self.conn2 = self.container2.create_connection("conn2",
                                                       self.conn2_handler)
        self.conn2.open()

    def process_connections(self, timestamp=None):
        common.process_connections(self.conn1, self.conn2, timestamp)

    def teardown(self):
        if self.conn1:
            self.conn1.destroy()
        if self.container1:
            self.container1.destroy()
        if self.conn2:
            self.conn2.destroy()
        if self.container2:
            self.container2.destroy()

    def _setup_sender_sync(self):
        """Create links, initiated by sender."""
        sl_handler = common.SenderCallback()
        sender = self.conn1.create_sender("src", "tgt", sl_handler)
        sender.user_context = sl_handler
        sender.open()
        self.process_connections()

        assert self.conn2_handler.receiver_requested_ct == 1
        args = self.conn2_handler.receiver_requested_args[0]
        rl_handler = common.ReceiverCallback()
        receiver = self.conn2.accept_receiver(args.link_handle,
                                              event_handler=rl_handler)
        receiver.user_context = rl_handler
        receiver.open()
        self.process_connections()
        assert receiver.active and rl_handler.active_ct > 0
        assert sender.active and sl_handler.active_ct > 0
        return (sender, receiver)

    def _setup_receiver_sync(self):
        """Create links, initiated by receiver."""
        rl_handler = common.ReceiverCallback()
        receiver = self.conn2.create_receiver("tgt", "src", rl_handler)
        receiver.user_context = rl_handler
        receiver.open()
        self.process_connections()

        assert self.conn1_handler.sender_requested_ct == 1
        args = self.conn1_handler.sender_requested_args[0]
        sl_handler = common.SenderCallback()
        sender = self.conn1.accept_sender(args.link_handle,
                                          event_handler=sl_handler)
        sender.user_context = sl_handler
        sender.open()
        self.process_connections()
        assert sender.active and sl_handler.active_ct > 0
        assert receiver.active and rl_handler.active_ct > 0
        return (sender, receiver)

    def test_create_destroy(self):
        sender = self.conn1.create_sender("source-addr", "target-addr",
                                          name="my-name")
        sender.user_context = "whatever"
        assert sender.name == "my-name"
        assert sender.source_address == "source-addr"
        assert sender.target_address is None

        receiver = self.conn2.create_receiver("target-addr", "source-addr",
                                              name="other-name")
        receiver.user_context = "meh"
        assert receiver.name == "other-name"
        assert receiver.target_address == "target-addr"
        assert receiver.source_address is None
        sender.destroy()
        receiver.destroy()

    def test_sender_setup_sync(self):
        sender, receiver = self._setup_sender_sync()
        sl_handler = sender.user_context
        rl_handler = receiver.user_context
        sender.close()
        self.process_connections()
        assert sl_handler.closed_ct == 0
        assert rl_handler.remote_closed_ct == 1
        assert rl_handler.remote_closed_error is None
        receiver.close()
        self.process_connections()
        assert sl_handler.closed_ct == 1
        assert sl_handler.remote_closed_ct == 0
        assert rl_handler.closed_ct == 1

    def test_sender_close_cond_sync(self):
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        cond = Condition("bad", "hate you",
                         {"yo-mama": "wears army boots"})
        sender.close(cond)
        self.process_connections()
        assert rl_handler.remote_closed_ct == 1
        assert rl_handler.remote_closed_error
        r_cond = rl_handler.remote_closed_error
        assert r_cond.name == "bad"
        assert r_cond.description == "hate you"
        assert r_cond.info.get("yo-mama") == "wears army boots"

    def test_receiver_setup_sync(self):
        sender, receiver = self._setup_receiver_sync()
        sl_handler = sender.user_context
        rl_handler = receiver.user_context
        receiver.close()
        self.process_connections()
        assert sl_handler.remote_closed_ct == 1
        assert sl_handler.remote_closed_error is None
        sender.close()
        self.process_connections()
        assert rl_handler.closed_ct == 1
        assert rl_handler.remote_closed_ct == 0
        assert sl_handler.closed_ct == 1

    def test_receiver_close_cond_sync(self):
        sender, receiver = self._setup_receiver_sync()
        sl_handler = sender.user_context
        cond = Condition("meh", "blah",
                         {"dog": "cat"})
        receiver.close(cond)
        self.process_connections()
        assert sl_handler.remote_closed_ct == 1
        assert sl_handler.remote_closed_error
        r_cond = sl_handler.remote_closed_error
        assert r_cond.name == "meh"
        assert r_cond.description == "blah"
        assert r_cond.info.get("dog") == "cat"

    def test_credit_sync(self):
        sender, receiver = self._setup_sender_sync()
        sl_handler = sender.user_context
        rl_handler = receiver.user_context
        assert receiver.capacity == 0
        receiver.add_capacity(3)
        assert receiver.capacity == 3
        assert sender.credit == 0
        assert sl_handler.credit_granted_ct == 0
        self.process_connections()
        # verify credit is sent to sender:
        assert sender.credit == 3
        assert sl_handler.credit_granted_ct == 1
        receiver.add_capacity(1)
        self.process_connections()
        assert receiver.capacity == 4
        assert sender.credit == 4
        # callback only occurs when credit is no longer zero:
        assert sl_handler.credit_granted_ct == 1
        assert sender.pending == 0
        msg = Message()
        msg.body = "Hi"
        sender.send(msg)
        # none pending because credit was consumed
        assert sender.credit == 3
        assert sender.pending == 0
        self.process_connections()
        # verify receiver's capacity decreases on send:
        assert receiver.capacity == 3
        assert rl_handler.message_received_ct == 1
        assert sender.credit == 3
        assert sender.pending == 0
        while sender.credit != 0:
            sender.send(msg)
            self.process_connections()
        assert receiver.capacity == 0
        assert rl_handler.message_received_ct == 4
        # verify no msgs sent if no credit:
        sender.send(msg)
        sender.send(msg)
        self.process_connections()
        assert sender.pending == 2
        assert sl_handler.credit_granted_ct == 1
        receiver.add_capacity(1)
        self.process_connections()
        assert receiver.capacity == 0
        assert rl_handler.message_received_ct == 5
        assert sender.credit == 0
        assert sender.pending == 1
        assert sl_handler.credit_granted_ct == 1

        receiver.add_capacity(1)
        self.process_connections()
        assert sender.credit == 0
        assert sender.pending == 0
        assert sl_handler.credit_granted_ct == 1

        # verify new credit becomes available:
        receiver.add_capacity(1)
        self.process_connections()
        assert sender.credit == 1
        assert sl_handler.credit_granted_ct == 2

    def test_send_presettled(self):
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg)
        receiver.add_capacity(1)
        self.process_connections()
        assert rl_handler.message_received_ct == 1
        msg2, handle = rl_handler.received_messages[0]
        assert msg2.body == "Hi"
        receiver.message_accepted(handle)

    def test_send_accepted(self):
        cb = common.DeliveryCallback()
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, cb, "my-handle")
        self.process_connections()
        assert rl_handler.message_received_ct == 0
        receiver.add_capacity(1)
        self.process_connections()
        assert cb.link is None  # not acknowledged yet
        assert rl_handler.message_received_ct == 1
        msg2, handle = rl_handler.received_messages[0]
        receiver.message_accepted(handle)
        self.process_connections()
        assert cb.link == sender
        assert cb.handle == "my-handle"
        assert cb.status == dingus.SenderLink.ACCEPTED

    def test_send_released(self):
        cb = common.DeliveryCallback()
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, cb, "my-handle")
        receiver.add_capacity(1)
        self.process_connections()
        assert rl_handler.message_received_ct == 1
        msg2, handle = rl_handler.received_messages[0]
        receiver.message_released(handle)
        self.process_connections()
        assert cb.link == sender
        assert cb.handle == "my-handle"
        assert cb.status == dingus.SenderLink.RELEASED

    def test_send_rejected(self):
        cb = common.DeliveryCallback()
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, cb, "my-handle")
        receiver.add_capacity(1)
        self.process_connections()
        assert rl_handler.message_received_ct == 1
        msg2, handle = rl_handler.received_messages[0]
        cond = Condition("itchy", "Needs scratching",
                         {"bath": True})
        receiver.message_rejected(handle, cond)
        self.process_connections()
        assert cb.link == sender
        assert cb.handle == "my-handle"
        assert cb.status == dingus.SenderLink.REJECTED
        r_cond = cb.info.get("condition")
        assert r_cond and r_cond.name == "itchy"

    def test_send_modified(self):
        cb = common.DeliveryCallback()
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, cb, "my-handle")
        receiver.add_capacity(1)
        self.process_connections()
        assert rl_handler.message_received_ct == 1
        msg2, handle = rl_handler.received_messages[0]
        annotations = {"dog": 1, "cat": False}
        receiver.message_modified(handle, False, True, annotations)
        self.process_connections()
        assert cb.link == sender
        assert cb.handle == "my-handle"
        assert cb.status == dingus.SenderLink.MODIFIED
        assert cb.info.get("delivery-failed") is False
        assert cb.info.get("undeliverable-here") is True
        info = cb.info.get("message-annotations")
        assert info and info["dog"] == 1

    def test_send_expired_no_credit(self):
        cb = common.DeliveryCallback()
        sender, receiver = self._setup_receiver_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, cb, "my-handle", deadline=10)
        # receiver.add_capacity(1)
        self.process_connections(timestamp=9)
        assert rl_handler.message_received_ct == 0
        assert sender.pending == 1
        assert cb.status is None
        self.process_connections(timestamp=10)
        assert sender.pending == 0
        assert cb.status == dingus.SenderLink.TIMED_OUT

    def test_send_expired_late_reply(self):
        cb = common.DeliveryCallback()
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        receiver.add_capacity(1)
        self.process_connections(timestamp=1)
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, cb, "my-handle", deadline=10)
        self.process_connections(timestamp=9)
        assert rl_handler.message_received_ct == 1
        assert sender.pending == 1
        assert sender.credit == 0
        assert cb.status is None
        self.process_connections(timestamp=10)
        assert rl_handler.message_received_ct == 1
        assert sender.pending == 0
        assert cb.status == dingus.SenderLink.TIMED_OUT
        # late reply:
        assert cb.count == 1
        msg2, handle = rl_handler.received_messages[0]
        receiver.message_accepted(handle)
        self.process_connections(timestamp=15)
        assert cb.count == 1

    def test_send_expired_no_reply(self):
        cb = common.DeliveryCallback()
        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, cb, "my-handle", deadline=10)
        self.process_connections(timestamp=1)
        assert rl_handler.message_received_ct == 0
        assert sender.pending == 1
        assert sender.credit == 0
        assert cb.count == 0
        receiver.add_capacity(1)
        self.process_connections(timestamp=2)
        assert rl_handler.message_received_ct == 1
        assert sender.pending == 1
        assert sender.credit == 0
        assert cb.count == 0
        self.process_connections(timestamp=12)
        assert sender.pending == 0
        assert cb.count == 1
        assert cb.status == dingus.SenderLink.TIMED_OUT

    def test_send_expired_no_callback(self):
        sender, receiver = self._setup_receiver_sync()
        rl_handler = receiver.user_context
        msg = Message()
        msg.body = "Hi"
        sender.send(msg, deadline=10)
        assert sender.pending == 1
        self.process_connections(timestamp=12)
        assert rl_handler.message_received_ct == 0
        assert sender.pending == 0

    def test_send_deadline_idle(self):
        """Validate the connection's deadline processing."""

        self.setup(props={"idle-time-out": 99})

        sender1 = self.conn1.create_sender("src1", "tgt1")
        sender1.open()
        self.process_connections(timestamp=1)
        assert self.conn2_handler.receiver_requested_ct == 1
        args = self.conn2_handler.receiver_requested_args[0]
        receiver1 = self.conn2.accept_receiver(args.link_handle)
        receiver1.open()

        sender2 = self.conn1.create_sender("src2", "tgt2")
        sender2.open()
        self.process_connections(timestamp=1)
        assert self.conn2_handler.receiver_requested_ct == 2
        args = self.conn2_handler.receiver_requested_args[1]
        receiver2 = self.conn2.accept_receiver(args.link_handle)
        receiver2.open()

        self.process_connections(timestamp=1)
        assert self.conn1.deadline == 100.0

        msg = Message()
        msg.body = "Hi"
        sender1.send(msg, deadline=11)
        assert self.conn1.deadline == 11
        self.process_connections(timestamp=2)
        assert self.conn1.deadline == 11

        sender2.send(msg, deadline=7)
        assert self.conn1.deadline == 7
        self.process_connections(timestamp=7)
        assert self.conn1.deadline == 11
        self.process_connections(timestamp=11)
        assert self.conn1.deadline == 100

        # next send timeout after the idle keepalive:
        sender1.send(msg, deadline=101)
        self.process_connections(timestamp=11)
        assert self.conn1.deadline == 100

        # have remote send idle, next deadline should
        # be the pending send:
        self.process_connections(timestamp=self.conn2.deadline)
        assert self.conn1.deadline == 101

    def test_send_close_on_ack(self):
        """Verify that the sender can close itself when delivery complete."""
        class SendDoneCallback(common.DeliveryCallback):
            def __call__(self, link, handle, status, info):
                super(SendDoneCallback, self).__call__(link, handle,
                                                       status, info)
                # verify that we can safely close ourself, even if there is a
                # send that has not completed:
                cond = Condition("indigestion", "old sushi",
                                 {"smoked eel": "yummy"})
                link.close(cond)

        sender, receiver = self._setup_sender_sync()
        rl_handler = receiver.user_context
        receiver.add_capacity(1)
        msg = Message()
        msg.body = "Hi"
        cb = SendDoneCallback()
        sender.send(msg, cb, "my-handle")
        # no credit - this one won't get sent:
        sender.send(msg, cb, "my-handle")
        self.process_connections()
        assert sender.active
        assert rl_handler.message_received_ct == 1
        msg2, handle = rl_handler.received_messages[0]
        receiver.message_accepted(handle)
        self.process_connections()
        assert not sender.active
        assert cb.count == 2
        # last callback should be abort:
        cond = cb.info.get('condition')
        assert cond
        assert cond.name == "indigestion"
        assert cb.status == dingus.SenderLink.ABORTED
        receiver.close()
        self.process_connections()
        assert sender.closed