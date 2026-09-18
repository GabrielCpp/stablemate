import React, { useEffect, useState } from "react";
import { FlatList, Pressable, Text, View } from "react-native";
import { fetchWidgets } from "../api/client";
import type { Widget } from "../api/types";

// Mirrors app.js's three-state shape exactly: a populated list, the empty-state notice, or
// the error alert when api-service can't be reached — the same states, reached the same
// way, so the two surfaces can be read as making the same claims against one API.
type ListState = { kind: "populated"; widgets: Widget[] } | { kind: "empty" } | { kind: "error" };

export function WidgetListScreen({ navigation }: { navigation: { navigate: (route: string) => void } }) {
  const [state, setState] = useState<ListState>({ kind: "empty" });

  useEffect(() => {
    loadWidgets(setState);
  }, []);

  if (state.kind === "error") return renderErrorAlert();
  if (state.kind === "empty") return renderEmptyNotice(navigation);

  return (
    <View testID="widget-list-screen" style={{ padding: 16 }}>
      <FlatList
        testID="widget-table"
        data={state.widgets}
        keyExtractor={(w) => w.id}
        renderItem={({ item }) => (
          <View testID={`widget-row-${item.id}`}>
            <Text>{item.name}</Text>
            <Text>{item.quantity}</Text>
          </View>
        )}
      />
      <Pressable testID="new-widget-link" onPress={() => navigation.navigate("NewWidget")}>
        <Text>Add a widget</Text>
      </Pressable>
    </View>
  );
}

// Fetch-and-classify helper, pulled out of the component body the same way app.js keeps
// loadWidgets apart from the render it feeds — citable, and testable, on its own.
export async function loadWidgets(setState: (state: ListState) => void): Promise<void> {
  try {
    const widgets = await fetchWidgets();
    setState(widgets.length === 0 ? { kind: "empty" } : { kind: "populated", widgets });
  } catch {
    setState({ kind: "error" });
  }
}

// The empty-state branch: same string as app.js's empty notice, plus the same link to the
// new-widget screen index.html carries.
export function renderEmptyNotice(navigation: { navigate: (route: string) => void }) {
  return (
    <View testID="widget-list-screen" style={{ padding: 16 }}>
      <Text testID="empty-notice" role="status">
        No widgets are on file yet.
      </Text>
      <Pressable testID="new-widget-link" onPress={() => navigation.navigate("NewWidget")}>
        <Text>Add a widget</Text>
      </Pressable>
    </View>
  );
}

// The alert branch: same string as app.js's catch block writes into its `p[role="alert"]`.
export function renderErrorAlert() {
  return (
    <View testID="widget-list-screen" style={{ padding: 16 }}>
      <Text testID="widgets-alert" role="alert">
        Could not read the widget directory.
      </Text>
    </View>
  );
}
