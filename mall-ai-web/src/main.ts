import { createApp } from "vue";

import App from "./App.vue";
import OperationsPage from "./OperationsPage.vue";
import QualityPage from "./QualityPage.vue";
import ServiceOperationsPage from "./ServiceOperationsPage.vue";
import "./style.css";

const normalizedPath = window.location.pathname.replace(/\/+$/, "") || "/";
const page = normalizedPath === "/operations"
  ? OperationsPage
  : normalizedPath === "/quality"
    ? QualityPage
    : normalizedPath === "/service-operations"
      ? ServiceOperationsPage
      : App;
createApp(page).mount("#app");
