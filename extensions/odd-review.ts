import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { getMarkdownTheme } from '@earendil-works/pi-coding-agent';
import { Markdown, Text, matchesKey, truncateToWidth } from '@earendil-works/pi-tui';
import { registerOddReview } from '../src/command.js';

export default function oddReview(pi: ExtensionAPI) {
  registerOddReview(pi, { Markdown, Text, matchesKey, truncateToWidth, getMarkdownTheme });
}
