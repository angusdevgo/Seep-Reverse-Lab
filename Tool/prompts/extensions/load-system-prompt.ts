/**
 * System Prompt Loader Extension for Pi
 *
 * Allows configuring prompts via `system.md` without losing Pi's built-in
 * tool guidelines, documentation references, and operational instructions.
 *
 * Supported locations (checked in order):
 * 1. Current project: `./.pi/system.md` or `./system.md`
 * 2. User directory: `~/.pi/agent/system.md` or `~/.pi/system.md`
 */

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { BuildSystemPromptOptions, ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { getDocsPath, getExamplesPath, getReadmePath } from "@earendil-works/pi-coding-agent";

function buildDefaultPrompt(options: BuildSystemPromptOptions): string {
	const readmePath = getReadmePath();
	const docsPath = getDocsPath();
	const examplesPath = getExamplesPath();
	const tools = options.selectedTools || ["read", "bash", "edit", "write"];

	const visibleTools = tools.filter((name) => !!options.toolSnippets?.[name]);
	const toolsList =
		visibleTools.length > 0 ? visibleTools.map((name) => `- ${name}: ${options.toolSnippets![name]}`).join("\n") : "(none)";

	const guidelinesList: string[] = [];
	const guidelinesSet = new Set<string>();
	const addGuideline = (guideline: string) => {
		if (!guidelinesSet.has(guideline)) {
			guidelinesSet.add(guideline);
			guidelinesList.push(guideline);
		}
	};

	const hasBash = tools.includes("bash");
	const hasPowerShell = tools.includes("powershell");
	const hasGrep = tools.includes("grep");
	const hasFind = tools.includes("find");
	const hasLs = tools.includes("ls");

	if ((hasBash || hasPowerShell) && !hasGrep && !hasFind && !hasLs) {
		if (hasBash && hasPowerShell) {
			addGuideline("Use bash or PowerShell for file operations like listing, searching, and finding files");
		} else if (hasPowerShell) {
			addGuideline("Use PowerShell for file operations like listing, searching, and finding files");
		} else {
			addGuideline("Use bash for file operations like ls, rg, find");
		}
	}

	for (const guideline of options.promptGuidelines ?? []) {
		const normalized = guideline.trim();
		if (normalized.length > 0) {
			addGuideline(normalized);
		}
	}

	addGuideline("Be concise in your responses");
	addGuideline("Show file paths clearly when working with files");

	const guidelines = guidelinesList.map((g) => `- ${g}`).join("\n");

	return `You are an expert coding assistant operating inside pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.

Available tools:
${toolsList}

In addition to the tools above, you may have access to other custom tools depending on the project.

Guidelines:
${guidelines}

Pi documentation (read only when the user asks about pi itself, its SDK, extensions, themes, skills, or TUI):
- Main documentation: ${readmePath}
- Additional docs: ${docsPath}
- Examples: ${examplesPath} (extensions, custom tools, SDK)
- When reading pi docs or examples, resolve docs/... under Additional docs and examples/... under Examples, not the current working directory
- When asked about: extensions (docs/extensions.md, examples/extensions/), themes (docs/themes.md), skills (docs/skills.md), prompt templates (docs/prompt-templates.md), TUI components (docs/tui.md), keybindings (docs/keybindings.md), SDK integrations (docs/sdk.md), custom providers (docs/custom-provider.md), adding models (docs/models.md), pi packages (docs/packages.md), environment variables (docs/environment-variables.md)
- When working on pi topics, read the docs and examples, and follow .md cross-references before implementing
- Always read pi .md files completely and follow links to related docs (e.g., tui.md for TUI API details)`;
}

export default function loadSystemPrompt(pi: ExtensionAPI) {
	pi.on("before_agent_start", async (event) => {
		const { systemPrompt, systemPromptOptions } = event;

		// Find custom system.md files
		const candidates = [
			join(process.cwd(), ".pi", "system.md"),
			join(process.cwd(), "system.md"),
			join(homedir(), ".pi", "agent", "system.md"),
			join(homedir(), ".pi", "system.md"),
		];

		const customSections: string[] = [];
		const readFiles = new Set<string>();

		for (const candidate of candidates) {
			if (existsSync(candidate) && !readFiles.has(candidate.toLowerCase())) {
				readFiles.add(candidate.toLowerCase());
				try {
					const content = readFileSync(candidate, "utf-8").trim();
					if (content) {
						customSections.push(content);
					}
				} catch {
					// Ignore read errors
				}
			}
		}

		// On Windows, if ~/.pi/agent/system.md exists, Pi's native loader treats it as SYSTEM.md
		// and strips the default prompt (setting systemPromptOptions.customPrompt).
		// We detect this and reconstruct the full default prompt so nothing is lost.
		let basePrompt = systemPrompt;
		if (systemPromptOptions.customPrompt) {
			const reconstructedDefault = buildDefaultPrompt(systemPromptOptions);
			// If the native loader used customPrompt directly, replace it with the reconstructed base
			basePrompt = systemPrompt.replace(systemPromptOptions.customPrompt, reconstructedDefault);
			// Also add the customPrompt content if it wasn't already picked up
			if (!customSections.some((s) => s === systemPromptOptions.customPrompt?.trim())) {
				customSections.unshift(systemPromptOptions.customPrompt.trim());
			}
		}

		if (customSections.length === 0) {
			return;
		}

		return {
			systemPrompt: `${basePrompt}\n\n${customSections.join("\n\n")}`,
		};
	});
}
