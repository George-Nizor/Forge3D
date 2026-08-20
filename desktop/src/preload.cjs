"use strict";

const { contextBridge, ipcRenderer } = require("electron");

function invoke(channel) {
  return (payload) => ipcRenderer.invoke(channel, payload);
}

function subscribe(channel, listener) {
  if (typeof listener !== "function") throw new TypeError("Listener must be a function");
  const wrapped = (_event, payload) => listener(payload);
  ipcRenderer.on(channel, wrapped);
  return () => ipcRenderer.removeListener(channel, wrapped);
}

contextBridge.exposeInMainWorld("forge3d", Object.freeze({
  bootstrap: invoke("forge3d:bootstrap"),
  pickAttachments: invoke("forge3d:pick-attachments"),
  startRun: invoke("forge3d:start-run"),
  continueRun: invoke("forge3d:continue-run"),
  steer: invoke("forge3d:steer"),
  cancel: invoke("forge3d:cancel"),
  answerApproval: invoke("forge3d:approval"),
  duplicate: invoke("forge3d:duplicate"),
  archive: invoke("forge3d:archive"),
  trash: invoke("forge3d:trash"),
  artifactAction: invoke("forge3d:artifact-action"),
  repairPlugin: invoke("forge3d:repair-plugin"),
  refreshTools: invoke("forge3d:refresh-tools"),
  onState: (listener) => subscribe("forge3d:state", listener),
  onEvent: (listener) => subscribe("forge3d:event", listener),
  onApproval: (listener) => subscribe("forge3d:approval", listener),
  onError: (listener) => subscribe("forge3d:error", listener),
}));