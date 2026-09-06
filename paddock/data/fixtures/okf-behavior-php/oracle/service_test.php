<?php
// A dependency-free oracle: one TAP line per case, exit 1 when any case fails.
require __DIR__ . "/service.php";

$cases = [
    ["name" => "success", "items" => ["a", "b", "c"], "sent" => ["z"], "limit" => 2, "status" => "sent", "count" => 2, "after" => ["z", "a", "b"], "error" => ""],
    ["name" => "empty", "items" => [], "sent" => ["z"], "limit" => 2, "status" => "empty", "count" => 0, "after" => ["z"], "error" => ""],
    ["name" => "error", "items" => ["a"], "sent" => ["z"], "limit" => -1, "status" => "", "count" => 0, "after" => ["z"], "error" => "limit must be nonnegative"],
    ["name" => "empty-error", "items" => [], "sent" => ["z"], "limit" => -1, "status" => "", "count" => 0, "after" => ["z"], "error" => "limit must be nonnegative"],
    ["name" => "zero", "items" => ["a", "b"], "sent" => [], "limit" => 0, "status" => "sent", "count" => 0, "after" => [], "error" => ""],
    ["name" => "bounded", "items" => ["a", "b"], "sent" => [], "limit" => 5, "status" => "sent", "count" => 2, "after" => ["a", "b"], "error" => ""],
];

$failed = 0;
echo "TAP version 13\n1.." . count($cases) . "\n";
foreach ($cases as $index => $tc) {
    $sent = $tc["sent"];
    $problems = [];
    try {
        $result = dispatch($tc["items"], $sent, $tc["limit"]);
        if ($tc["error"] !== "") {
            $problems[] = "expected exception";
        } else {
            if ($result["status"] !== $tc["status"]) {
                $problems[] = "status " . var_export($result["status"], true);
            }
            if ($result["count"] !== $tc["count"]) {
                $problems[] = "count " . var_export($result["count"], true);
            }
        }
    } catch (InvalidArgumentException $e) {
        if ($tc["error"] === "" || $e->getMessage() !== $tc["error"]) {
            $problems[] = "exception " . $e->getMessage();
        }
    }
    if ($sent !== $tc["after"]) {
        $problems[] = "sent " . json_encode($sent);
    }
    $line = ($index + 1) . " - dispatch contract/" . $tc["name"];
    if ($problems === []) {
        echo "ok $line\n";
    } else {
        $failed++;
        echo "not ok $line # " . implode("; ", $problems) . "\n";
    }
}
exit($failed === 0 ? 0 : 1);
