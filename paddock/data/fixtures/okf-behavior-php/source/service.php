<?php
function dispatch(array $items, array &$sent, int $limit): array
{
    if ($limit < 0) {
        throw new InvalidArgumentException("limit must be nonnegative");
    }
    if (count($items) === 0) {
        return ["status" => "empty", "count" => 0];
    }
    $selected = array_slice($items, 0, min($limit, count($items)));
    array_push($sent, ...$selected);
    return ["status" => "sent", "count" => count($selected)];
}
