const { defineConfig, globalIgnores } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');
const prettierConfig = require('eslint-config-prettier/flat');

module.exports = defineConfig([
  globalIgnores(['dist/*', '.expo/*', 'expo-env.d.ts']),
  expoConfig,
  // Formatting is Prettier's job (`npm run format:check`); disable conflicting rules.
  prettierConfig,
]);
