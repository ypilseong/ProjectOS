import { Plugin } from "obsidian";

export default class ProjectOSPlugin extends Plugin {
  async onload(): Promise<void> {
    console.log("ProjectOS plugin loaded");
  }
}
