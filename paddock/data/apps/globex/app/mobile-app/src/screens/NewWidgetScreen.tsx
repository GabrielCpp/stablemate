import React, { useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { createWidget } from "../api/client";
import type { FieldErrors } from "../api/types";

export function NewWidgetScreen({ navigation }: { navigation: { navigate: (route: string) => void } }) {
  const [name, setName] = useState("");
  const [quantity, setQuantity] = useState("0");
  const [errors, setErrors] = useState<FieldErrors>({});

  const onSubmit = async () => {
    setErrors({});
    const result = await submitNewWidget(name, Number(quantity));
    if (result.ok) {
      navigation.navigate("WidgetList");
      return;
    }
    setErrors(result.errors);
  };

  return (
    <View testID="new-widget-screen" style={{ padding: 16 }}>
      <Text>Name</Text>
      <TextInput testID="name-input" value={name} onChangeText={setName} />
      {renderFieldError("name-error", errors.name)}
      <Text>Quantity</Text>
      <TextInput testID="quantity-input" value={quantity} onChangeText={setQuantity} keyboardType="numeric" />
      {renderFieldError("quantity-error", errors.quantity)}
      <Pressable testID="submit-widget" onPress={onSubmit}>
        <Text>Add widget</Text>
      </Pressable>
    </View>
  );
}

// Same job as new.js's submitNewWidget: POST straight to api-service and hand back either
// the created widget or the field errors from its 422 body. Pulled out of the component so
// the submit behaviour is citable, and testable, apart from the rendering around it.
export async function submitNewWidget(name: string, quantity: number) {
  return createWidget(name, quantity);
}

// Renders one field's inline error, or nothing when there isn't one — the same split
// new.js keeps between clearFieldErrors and showFieldErrors, collapsed into one helper
// since React re-renders the whole tree rather than mutating two spans in place.
export function renderFieldError(testID: string, message?: string) {
  if (!message) return null;
  return (
    <Text testID={testID} role="alert">
      {message}
    </Text>
  );
}
