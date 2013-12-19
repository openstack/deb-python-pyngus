# fusion #

A connection oriented messaging framework built around the QPID Proton engine.

# Purpose #

This framework is meant to ease the integration of AMQP 1.0 messaging
into existing applications.  It provides a very basic,
connection-oriented messaging model that should meet the needs of most
applications.

The framework has been designed with the following goals in mind:

* simplify the user model exported by the Proton engine - you should
not have to be an expert in AMQP to use this framework!

* give the application control of the I/O implementation where
  possible

* limit the functionality provided by Proton to a subset that
should be adequate for 79% of all messaging use-cases [1]


All actions are designed to be non-blocking,
leveraging callbacks where asynchronous behavior is modeled.

There is no threading architecture assumed or locking performed by
this framework.  Locking is assumed to be handled outside of this
framework by the application - all processing provided by this
framework is assumed to be single-threaded.

[1] If I don't understand it, it won't be provided. [2]  
[2] Even if I do understand it, it may not be provided [3]  
[3] Ask yourself: Is this feature *critical* for the simplest messaging task?

## What this framework doesn't do ##

* Message management.  All messages are assumed to be Proton Messages.
  Creating and parsing Messages is left to the application.

* Routing. This framework assumes link-based addressing.  What does
  that mean?  It means that this infrastructure basically ignores the
  "to" or "reply-to" contained in the message.  It leaves these fields
  under the control and interpretation of the application.  This
  infrastructure requires that the application determines the proper
  Link over which to send an outgoing message.  In addition, it assumes
  the application can correlate messages arriving on a link.

* Connection management.  It is expected that your application will
  manage the creation and configuration of sockets. Whether those
  sockets are created by initiating a connection or accepting an
  inbound connection is irrelevant to the framework.  It is also
  assumed that, if desired, your application will be responsible for
  monitoring the sockets for I/O activity (e.g. call poll()).  The
  framework will support both blocking and non-blocking sockets,
  however it may block when doing I/O over a blocking socket.  Note
  well: reconnect and failover must also be handled by the application.

* Flow control. It is assumed the application will control the number
  of messages that can be accepted by a receiving link (capacity).
  Sent messages will be queued locally until credit is made availble
  for the message(s) to be transmitted.  The framework's API allows
  the application to monitor the number of outbound messages queued on
  an outgoing link.


# Theory of Operations #

This framework defines the following set of objects:

 * Container - an implementation of the container concept defined by AMQP 1.0.
      An instance must have a name that is unique across the entire
      messaging domain, as it is used as part of the address.  This
      object is a factory for Connections.

 * Connection - an implementation of the connection concept defined by AMQP
       1.0.  You can think of this as a pipe between two Containers.
       When creating a Connection, your application must provide a
       socket (or socket-like object).  That socket will be
       responsible for handling data travelling over the Connection.

 * ResourceAddress - an identifier for a resource provided by a
       Container.  Messages may be consumed from, or sent to, a
       resource.

 * Links - A uni-directional pipe for messages traveling between
       resources.  There are two sub-classes of Links: SenderLinks and
       ReceiverLinks.  SenderLinks produce messages from a particular
       resource.  ReceiverLinks consume messages generated from a particular
       resource.

And application creates one or more Containers, which represents a
domain for a set of message-oriented resources (queues, publishers,
consumers, etc) offered by the application.  The application then
forms network connections with other systems that offer their own
containers.  The application may initiate these network connections
(eg. call connect()), or listen for connection requests from remote
systems (eg. listen()/accept()) - this is determined by the
application's design and purpose.

The method used by the application to determine which systems it
should connect to in order to access particular resources and
Containers is left to the application designers.

Once these network connections are initiated, the application can
allocate a Connection object from the local Container.  This
Connection object represents the data pipe between the local and
remote Containers.  The application must provide a network socket to
the Connection constructor. This socket is used by the framework for
communicating over the Connection.

If the application needs to send messages to a resource on the remote
Container, it allocates a SenderLink from the Connection to the remote
Container.  The application assigns a local name to the SenderLink
that identifies the resource that is the source of the sent messages.
This is the Source resource address, and is made available to the
remote so it may classify the origin of the message stream.  The
application may also supply the address of the resource to which it is
sending.  This is the Target resource address.  The Target resource
address may be overridden by the remote.  If no Target address is
given, the remote may allocate one on behalf of the sending
application.  The SenderLink's final Target address is made available
to the sending application once the link has completed setup.

When sending a message, an application can choose whether or not it
wants to know about the arrival of the message at the remote resource.
The application may send the message as "best effort" if it doesn't
need to know if the message arrived at the remote resource.  This
'send-and-forget' service provides no feedback on the delivery of the
message.  Otherwise, the application may register a callback that is
invoked when the delivery status of the message is updated by the
remote resource.

If the application needs to consume messages from a resource on the
remote Container, it allocates a ReceiverLink from the Connection to
the remote Container.  The application assigns a local name to the
ReceiverLink that identifies the local resource that is the consumer
of all the messages that arrive on the link.  This is the Target
resource address, and is made available to the remote so it may
classify the destination of the message stream.  The application may
also supply the address of the remote resource from which it is
consuming.  This is the Source resource address.  The Source resource
address may be overridden by the remote.  If no Source address is
given, the remote may allocate one on behalf of the receiving
application.  The ReceiverLink's final Source address is made
available to the receiving application once the link has completed
setup.

# API #

## Container ##

`Container( name, containerEventHandler, properties={} )`

Construct a container.  Parameters:

* name - identifier for the new container, MUST BE UNIQUE across the
entire messaging domain.
* containerEventHandler - callbacks for container events (see below)
* properties - map, contents TBD


`Container.create_connection( name, ConnectionEventHandler, properties={}...)`

The factory for Connection objects. Parameters:

* name - uniquely identifies this connection within the Container
* properties - map containing the following optional connection
  attributes:
   * "remote-hostname" - DNS name of remote host.
   * "idle-time-out" - time in milliseconds before connection is
  closed due to lack of traffic.  Setting this may enable heartbeat
  generation by the peer, if implemented.
   * "sasl" - map of sasl configuration stuff (need callbacks, TBD)
   * "ssl" - ditto, future-feature


`Container.need_io()`

 Returns a pair of lists containing those connections that are read blocked and write-ready.


`Container.next_tick()`

Return the timestamp of the next pending timer event to expire. In
seconds since Epoch.  Your application must call Container.process_tick()
at least once at or before this timestamp expires!


`Container.process_tick(now)`

Does all timer related processing for all of the Connections held by
this Container.  Returns a list of all the Connections which had
timers expire.  You must call `Container.process_tick()` after this
call to determine the deadline for the next call to `process_tick()`
should be made.


`Container.resolve_sender(target-address)`

Find the SenderLink that sends to the remote resource with the address
*target-address*


`Container.resolve_receiver(source-address)`

Find the ReceiverLink that consumes from the remote resource with the
address *source-address*


`Container.get_connection(connection-name)`

Return the Connection identified by <connection-name>


### ContainerEventHandler ###

The ContainerEventHandler passed on container construction has the following callback methods that your application can register:

**TBD**


## Connection ##

No public constructor - use Container.create_connection().


`Connection.tick(now)`

Updates any protocol timers running in the connection, and returns the expiration time of the next pending timer.

* now: seconds since Epoch
* returns: a timestamp, which is the deadline for the next expiring timer in seconds since Epoch.  Zero if no active timers.


`Connection.next_tick()`

Returns the last value returned from the `Connection.tick()` call.


`Connection.needs_input()`

Returns the number of bytes of inbound network data this connection
can process.  Returns zero if no input can be processed at this time.
Returns `EOS` when the input pipe has been closed.


`Connection.process_input(data)`

Process data read from the network.  Returns the number of bytes from
`data` that have been processed, which will be no less than the last
value returned from `Connection.need_input()`.  Returns EOS if the
input pipe has been closed.


`Connection.input_closed(reason)`

Indicates to the framework that the read side of the network
connection has closed.


`Connection.has_output()`

Returns the number of bytes of output data the connection has
buffered.  This data needs to be written to the network.  Returns zero
when no pending output is available.  Returns EOS when the output pipe
has been closed.


`Connection.output_data()`

Returns a buffer containing data that needs to be written to the
network.  Returns None if no data or the output pipe has been closed.


`Connection.output_written(N)`

Indicate to the framework that N bytes of output data (as given by
`Connection.output_data()`) has been written to the network.  This
will cause the framework to release the first N bytes from the buffer
output data - allowing the framework to generate more output.


`Connection.output_closed(reason)`

Indicates to the framework that the write side of the network
connection has closed.

`Connection.destroy(error=None)`

Close the network connection, and force any in-progress message
transfers to abort.  Deletes the Connection (and all underlying Links)
from the Container.  The socket is closed as a result of this method.
Parameters:
* error - optional error, supplied by application if closing due to an unrecoverable error.


`Connection.create_sender( source-resource, target-resource=None,
                           senderEventHandler, properties={})`

Construct a SenderLink using this connection which will send messages
to the *target-resource* on the remote.  If *target-resource* is None,
the remote may generate one.  The address of a dynamically-created
Target will be made available via the SenderLink once the link is
active.  Parameters:

* source-resource - resource address of the local resource that is
  generating the messages sent on this link.  This address may be
  prefixed with the local containter name.
* target-resource - resource address of the destination resource that
  is to consume the sent messages. May be None if the remote can
  dynamically allocate a resource for the target.  The resource
  address may be prefixed with the remote container name.
* senderEventHandler - a set of callbacks for monitoring the state of
  the link.  See below.
* properties - map of optional properties *TBD*


`Connection.accept_sender(sender-info, ... TBD)`

Accept a remotely-requested SenderLink and construct it (see the
ConnectionEventHandler.sender_request() method below).


`Connection.reject_sender(sender-info, reason, ... TBD)`

Reject a remotely-requested SenderLink (see the
ConnectionEventHandler.sender_request() method below)


`Connection.create_receiver( target-resource, source-resource=None,
                             receiverEventHandler, properties={})`

Construct a ReceiverLink using this connection which will consume
messages from the *source-resource* on the remote.  If
*source-resource* is None, the remote may generate one.  The address
of the dynamically-created Source will be made available via the
ReceiverLink once the link is active.  Parameters:

* target-resource - resource address of the local resource that is
  consuming the messages arriving on the link.
* source-resource - resource address of the remote resource that is
  generating the messages arriving on the link. May be None if the
  remote can dynamically allocate a resource for the source.  The
  resource address may be prefixed with the remote container name.
* receiverEventHandler - a set of callbacks for receiving messages and
  monitoring the state of the link.  See below.
* properties - map of optional properties, including:
    * capacity - maximum number of incoming messages this receiver can
      buffer.


`Connection.accept_receiver(receiver-info, ... TBD)`

Accept a remotely-requested ReceiverLink and construct it (see the
ConnectionEventHandler.receiver_request() method below).


`Connection.reject_receiver(receiver-info, reason)`

Reject a remotely-requested ReceiverLink (see the
ConnectionEventHandler.sender_request() method below)


### ConnectionEventHandler ###

The ConnectionEventHandler passed on connection construction has the
following callback methods that your application can register:


`ConnectionEventHandler.connection_active(connection)`

Called when the connection transitions to up.

* connection - the Connection


`ConnectionEventHandler.connection_closed(connection, error-code)`

Called when connection has been closed by peer.  Error-code provided
by peer (optional).

* connection - the Connection


`ConnectionEventHandler.receiver_request(connection, source-resource,
                                         target-resource, receiver-info, ...)`

The peer is attempting to create a new ReceiverLink so it can
send messages to a resource in the local container.  This resource is
identified by *target-resource*.  Your application must accept or
reject this request.  If *target-resource* is None, the peer is
requesting your application generate a resource - your application
must provide the address of this resource should you accept this
ReceiverLink.  Parameters:

* connection - the Connection
* source-resource - the address of the remote resource that will
  generate the arriving messages.
* target-resource - the requested address of the local resource that
  will be consuming the inbound messages.  May be overridden by the
  application.
* receiver-info *TBD*


`ConnectionEventHandler.sender_request( connection, target-resource,
                                        source-resource, sender-info, ...)`

The peer is attempting to create a new SenderLink so it can consume
messages from a resource in the local container.  This resource is
identified by *source-resource*.  Your application must accept or
reject this request.  If *source-resource* is None, the peer is
requesting your application generate a resource - your application
must provide the address of this resource should you accept this
SenderLink.

* connection - the Connection
* target-resource - the address of the remote resource that will
  consume the arriving messages.
* source-resource - the requested address of the local resource that
  will be generating the outbound messages.  May be overridden by the
  application.
* sender-info *TBD*


**TBD - what about SASL result?**

**TBD - what about SSL (if not already provided with socket)?**



## SenderLink ##

No public constructor - use Connector.create_sender() for creating a
local sender or `Connector.accept_sender()` to establish a
remotely-requested one.

`SenderLink.send( Message, DeliveryCallback=None, handle=None, deadline=None )`

Queue a message for sending over the link.  *Message* is a Proton
Message object.  If there is no need to know the delivery status of
the message at the peer, then DeliveryCallback, handle, and deadline
should not be provided.  In this case, the message will be sent
"pre-settled".  To get notification on the delivery status of the
message, a callback and handle must be supplied.  The deadline is
optional in this case.  This method returns 0 if the message was
queued successfully (and the callback, if supplied, is guaranteed to
be invoked).  Otherwise the message was not queued and no callback
will be made.  Parameters:

* Message - a complete Proton Message object
* handle - opaque object supplied by application.  Passed to
  DeliveryCallback method.
* deadline - future timestamp when send should be aborted if not
  completed. In seconds since Epoch.
* DeliveryCallback( SenderLink, handle, status, reason=None ) -
  optional, invoked when the send operation completes.  The status
  parameter will be one of:
   * TIMED_OUT - send did not complete before deadline hit, send aborted (locally generated)
   * ACCEPTED - remote has received and accepted the message
   * REJECTED - remote has received but has rejected the message
   * RELEASED - see 'ReceiverLink.message_released()`
   * MODIFIED - see 'ReceiverLink.message_modified()`
   * ABORTED - connection or sender has been forced closed/destroyed,
     etc. (locally generated) In this case, the reason parameter may be set to an error
     code.
   * UNKNOWN - the remote did not provide a delivery status.


`SenderLink.pending()`

Returns the number of outging messages in the process of being sent.


`SenderLink.credit()`

Returns the number of messages the remote ReceiverLink has permitted
the SenderLink to send.


`SenderLink.destroy(error)`

Close the link, and force any in progress message transfers to abort.
Deletes the SenderLink from the Container.  Parameters:

* error - optional error, supplied by application if closing due to an
  unrecoverable error.


### SenderEventHandler ###

The SenderEventHandler can be passed to the SenderLink's constructor, and has the
following callback methods that your application can register:


`SenderEventHandler.sender_active(SenderLink)`

Called when the link protocol has completed and the SenderLink is active.


`SenderEventHandler.sender_closed(SenderLink, error-code)`

Called when connection has been closed by peer, or due to close of the
owning Connection.  Error-code provided by peer (optional)


## ReceiverLink ##

No public constructor - use Connector.create_receiver() for creating a
local receiver or `Connector.accept_receiver()` to establish a
remotely-requested one.


`ReceiverLink.capacity()`

Returns the number of messages the ReceiverLink is able to queue
locally before back-pressuring the sender.  Capacity decreases by one
each time a Message is consumed.


`ReceiverLink.add_capacity(N)`

Increases capacity by N messages.  Must be called by application to
replenish credit as messages arrive.


`ReceiverLink.message_accepted( msg-handle )`

Indicate to the remote that the message identified by msg-handle has
been successfully processed by the application (See
ReceiverEventHandler below).


`ReceiverLink.message_rejected( msg-handle, reason )`

Indicate to the remote that the message identified by msg-handle is
considered invalid by the application and has been rejected (See
ReceiverEventHandler below).


`ReceiverLink.message_released( msg-handle, reason )`

Indicate to the remote that the message identified by msg-handle will
not be processed by the application (See ReceiverEventHandler below).


`ReceiverLink.message_modified( msg-handle, reason )`

Indicate to the remote that the message identified by msg-handle was
modified by the application, but not processed (See
ReceiverEventHandler below).


`ReceiverLink.destroy(error)`

Close the link, terminating any further message deliveries. Deletes the ReceiverLink from the Container.  Parameters:

* error - optional error, supplied by application if closing due to an
  unrecoverable error.


### ReceiverEventHandler ###

Passed to ReceiverLink constructor.  Has the following callback
methods that your application can register:


`ReceiverEventHandler.receiver_active(ReceiverLink)`

Called when the link protocol has completed and the ReceiverLink is active.


`ReceiverEventHandler.receiver_closed(ReceiverLink, error-code)`

Called when connection has been closed by peer, or due to close of the
owning Connection.  Error-code provided by peer (optional)


`ReceiverEventHandler.message_received(ReceiverLink, Message, msg-handle)`

Called when a Proton Message has arrived on the link.  Use msg-handle
to indicate whether the message has been accepted or rejected by
calling `ReceiverLink.accept_message()` or `ReceiverLink.reject_message()`
as appropriate.  The capacity of the link will be decremented by one
on return from this callback. Parameters:

* ReceiverLink - link which received the Message
* Message - a complete Proton Message
* msg-handle - opaque handle used by framework to coordinate the
  message's receive status.


## ResourceAddress ##

**TBD: this needs more thought**

The address for a resource is comprised of four parts:

* *transport address* - identifies the host of the Container on the
  network.  Typically this is the DNS hostname, with optional port.
* *container identifier* - the identifier of the Container as
   described above.  This is represented by a string, and must be
   unique across the messaging domain.
* *resource identifier* - the identifer of a resource within the
   Container.  Represented as a string value.
* property map - an optional map of address properties TBD

The ResourceAddress can be represented in a string using the following syntax:

    *amqp://[user:password@]<transport-address>/<container-id>/<resource-id>[; {property-map}*

where:

* [user:password@] - used for authentication
* transport-address - a DNS hostname.  Largely ignored by this
 framework, as socket configuration is provided by the application.
* container-id - string, not containing '/' character.  The framework
  will use this for a part of the Target and Source resource
  address.
* resource-id - string, not containing ';' character.  The framework
  will use this when creating Target and Source addresses for
  resources.
* property-map - TBD

Example:

    "amqp://localhost.localdomain:5672/my-container/queue-A ; {mode: browse}"

When creating local Target and Source resources, this framework will
assign an address that will be used to identify these resources within
the messaging domain.  The resource address will be a string using the
following format:

    /container-id/resource-id

These strings will be used to set the Target and Source address fields
in the link Attach frame as described by the AMQP 1.0 standard for
locally-maintained resources.  The format and syntax of resources
maintained by the peer may not be defined by this framework.  This
framework will make no attempt to parse such remotely generated
resource addresses - they will be treated simply as opaque string
values.


For the most part, *transport-address* is ignored by the infrastructure.

