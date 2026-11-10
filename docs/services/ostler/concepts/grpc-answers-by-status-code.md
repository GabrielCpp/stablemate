---
type: concept
slug: grpc-answers-by-status-code
title: A gRPC answer is named by its status code
---
# A gRPC answer is named by its status code

A service book declares a unary gRPC call as one `Rpc` class, named by `package.Service/Method` as the proto file has it. The request message is the body, and the call has everything an HTTP endpoint has: its input classes, its witness and the model action it carries. The runtime sends the call through `grpcurl`, which reads the service's own description by reflection, so a book needs no generated code. The binary must be on `PATH` and the service must serve reflection.

An answer is named by its status code, `Code.OK`, `Code.NOT_FOUND` or `Code.FAILED_PRECONDITION`, never by a number. A rule, a defect and a refusal take the same `Code`. Every answer that is not `Code.OK` has the shape of the status message the service gave.

A field is named as the proto file names it, `team_id`, in a request, in an answer and in a fixture. The JSON spelling `teamId` appears nowhere in a book. A field whose proto name is a Python keyword takes an underscore in the fixture, so `from` is written `from_`, and the wire and the report say `from`. A 64-bit integer travels as text and reads back as a number. A nested message is a nested fixture, packed by the shape the body declares.

A scalar is always there on the wire: the service sends a zero value as an empty string, 0 or false, so the model says the zero value and the field is not nullable. A message or a timestamp nobody set reads as null and is declared nullable.

The credential of a call reaches `grpcurl` through its environment and never on its command line. A refusal is read from the status the binary prints. A binary that is not on `PATH` is reported as a book error, and a call to a service that does not answer is a place that cannot be judged.

- code: ostler/ostler/book/status.py::Code@ab5a9854eef3
- code: ostler/ostler/book/rpc.py::Rpc@ea94cdecd61a
- code: ostler/ostler/book/rpc.py::GrpcClient@2c8aace46e34
- code: ostler/ostler/book/rpc.py::proto_named@ec1cfe2cc52d
- rule: a gRPC answer is named by its status code, and a number is never written for one
- rule: a field is named as the proto file names it in every request, answer and fixture
- rule: a scalar is always present on the wire, so the model holds its zero value and never marks it nullable
- rule: a 64-bit integer is a number in an answer, although it travels as text
- rule: the credential travels in the environment of `grpcurl` and never on its command line
- rule: a missing `grpcurl` is a book error and never a verdict on the service
- rule: an id that filters a list names nothing and still answers OK with an empty list, so each such input class is declared a divergence with its reason
- tests: ostler/tests/test_book_status.py::test_a_code_is_found_by_its_name
- tests: ostler/tests/test_book_status.py::test_ok_is_the_only_code_that_succeeded
- tests: ostler/tests/test_book_rpc.py::test_an_ok_answer_is_read_back_under_the_proto_names
- tests: ostler/tests/test_book_rpc.py::test_a_64_bit_integer_that_travels_as_text_is_a_number
- tests: ostler/tests/test_book_rpc.py::test_a_refusal_is_read_from_the_status_the_binary_prints
- tests: ostler/tests/test_book_rpc.py::test_the_credential_travels_in_the_environment_and_never_on_the_command_line
- tests: ostler/tests/test_book_rpc.py::test_a_missing_binary_is_reported_as_a_book_error
- tests: ostler/tests/test_book_http.py::test_a_keyword_field_goes_on_the_wire_without_its_underscore
