import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import { DataProvider } from "./lib/data";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import ShareOfVoice from "./pages/ShareOfVoice";
import Citations from "./pages/Citations";
import Focus from "./pages/Focus";
import Backlog from "./pages/Backlog";
import Calendar from "./pages/Calendar";

// HashRouter: GitHub Pages serves a static folder with no URL rewriting, so
// deep links must live in the fragment (#/focus) to survive a refresh.
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DataProvider>
      <HashRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="share-of-voice" element={<ShareOfVoice />} />
            <Route path="citations" element={<Citations />} />
            <Route path="focus" element={<Focus />} />
            <Route path="backlog" element={<Backlog />} />
            <Route path="calendar" element={<Calendar />} />
          </Route>
        </Routes>
      </HashRouter>
    </DataProvider>
  </StrictMode>,
);
