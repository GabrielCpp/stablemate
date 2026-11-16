"""The calls a contract file lists: the rpcs of a proto and the operations of an OpenAPI document."""

from __future__ import annotations

from ostler.book.contracts import Call, openapi_calls, proto_calls

PROTO = """
syntax = "proto3";
// package fake.v9;
package notifications.v1;

/* service Hidden { rpc Nope(A) returns (B); } */
service NotificationsService {
  // rpc Commented(A) returns (B);
  rpc Send(SendRequest) returns (SendResponse) {
    option (google.api.http) = { post: "/v1/{x}//send" body: "*" };
  }
  rpc StreamNotifications(StreamRequest) returns (stream Notification);
  rpc Upload(stream Chunk) returns (UploadResponse);
  rpc Chat (stream Line)
      returns (stream Line) {}
}

service Other {
  rpc Ping(google.protobuf.Empty) returns (google.protobuf.Empty);
}
"""

DOCUMENT = """
openapi: 3.0.0
paths:
  /todos:
    get: {}
    post: {}
    parameters: []
  /todos/{id}:
    delete: {}
"""

JSON_DOCUMENT = '{"swagger": "2.0", "basePath": "/api", "paths": {"/todos/{todo_id}": {"get": {}, "put": {}}}}'


def test_a_protos_rpcs_are_read_with_their_kind_and_comments_and_options_are_ignored():
    assert proto_calls(PROTO) == [
        Call("notifications.v1.NotificationsService/Send", "Send", ""),
        Call("notifications.v1.NotificationsService/StreamNotifications", "StreamNotifications", "answer"),
        Call("notifications.v1.NotificationsService/Upload", "Upload", "request"),
        Call("notifications.v1.NotificationsService/Chat", "Chat", "both"),
        Call("notifications.v1.Other/Ping", "Ping", ""),
    ]


def test_an_openapi_documents_operations_are_read_from_yaml():
    assert [c.name for c in openapi_calls(DOCUMENT)] == ["GET /todos", "POST /todos", "DELETE /todos/{id}"]


def test_an_openapi_documents_operations_are_read_from_json():
    assert [c.name for c in openapi_calls(JSON_DOCUMENT)] == ["GET /todos/{todo_id}", "PUT /todos/{todo_id}"]


def test_a_path_parameter_is_compared_by_its_position_and_not_its_name():
    first = openapi_calls(DOCUMENT)[0]
    [delete] = [c for c in openapi_calls(DOCUMENT) if c.name.startswith("DELETE")]
    assert delete.matches("DELETE", "/todos/{todo_id}")
    assert not delete.matches("DELETE", "/todos/{a}/{b}")
    assert first.matches("GET", "/todos")


def test_a_base_path_of_the_document_may_prefix_the_path_an_endpoint_declares():
    [get, _] = openapi_calls(JSON_DOCUMENT)
    assert get.matches("GET", "/api/todos/{id}")
