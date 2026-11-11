---
type: concept
slug: what-a-service-book-cannot-say-yet
title: What a service book cannot say yet
---
# What a service book cannot say yet

The format has edges. A call that needs one of these is left out of the book and reported, so the book never claims what a run cannot check.

- A breach, or a minute count at its exact boundary, needs a clock the book sets. The runtime cannot set the service's clock, so a value that moves with it is declared opaque with the reason. A request that pins the value, such as a window given by two instants in the past, is preferred to an opaque field.
- A call that streams its answer or its request has no declaration.
- Status details beyond the code and the message of a gRPC answer are not read.
- A defect whose own message quotes the request is not declared.
- A call of the book's own service whose effect lands after its answer is not waited for. Only an outside event is read again until it lands.
- Mobile surfaces arrive with a later release. The declarations of a screen exist, and `ostler book screens` prints them, but the runtime ships a driver for a web page only.
- A screen's components carry no shape, so the input classes and the twin pairs that an endpoint's body fields earn are not played on a web book.

- rule: a call the format cannot express is left out of the book and reported, and never approximated with a looser shape
- rule: a value the service's clock sets is declared opaque with its reason, and every such value is listed in the report
- rule: an HTTP or gRPC book makes no claim about a web or mobile surface
- rule: a web book plays its journeys and its lifecycle cells, and makes no claim about input classes or twin pairs of a screen's fields
- code: ostler/ostler/book/witness.py::Because@a08d2e476d9e
- code: ostler/ostler/book/screen.py::Screen@2ca061585fdf
- code: ostler/ostler/book/cli.py::cmd_screens@06efe5170dd7
