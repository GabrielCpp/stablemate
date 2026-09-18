import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { WidgetListScreen } from "./src/screens/WidgetListScreen";
import { NewWidgetScreen } from "./src/screens/NewWidgetScreen";

const Stack = createNativeStackNavigator();

// Navigation root: the same two screens web-app serves as index.html and new.html, wired
// as a stack instead of two static pages, against the one api-service both surfaces share.
export function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="WidgetList">
        <Stack.Screen name="WidgetList" component={WidgetListScreen} options={{ title: "Widget directory" }} />
        <Stack.Screen name="NewWidget" component={NewWidgetScreen} options={{ title: "Add a widget" }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export default App;
