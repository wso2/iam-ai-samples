// app/lib/schema-flattener.ts
/**
 * Utility to flatten JSON schemas by resolving $ref and removing $defs
 * This is needed for AI providers like Google Gemini that don't support JSON Schema references
 */

export interface JSONSchema {
  [key: string]: any;
}

/**
 * Flatten a JSON schema by resolving all $ref references
 * This creates a schema without $defs or $ref that's compatible with Gemini
 * 
 * @param schema - The JSON schema with potential $refs and $defs
 * @returns A flattened schema without references
 */
export function flattenSchema(schema: JSONSchema): JSONSchema {
  if (!schema || typeof schema !== 'object') {
    return schema;
  }

  // Clone the schema to avoid mutations
  const cloned = JSON.parse(JSON.stringify(schema));
  
  // Extract definitions for resolution
  const definitions = cloned.$defs || cloned.definitions || {};
  
  // Resolve all references
  const resolved = resolveReferences(cloned, definitions);
  
  // Remove $defs and definitions from the result
  delete resolved.$defs;
  delete resolved.definitions;
  
  return resolved;
}

/**
 * Recursively resolve $ref references in a schema
 */
function resolveReferences(
  obj: any,
  definitions: Record<string, any>,
  visited: Set<string> = new Set()
): any {
  if (!obj || typeof obj !== 'object') {
    return obj;
  }

  // Handle arrays
  if (Array.isArray(obj)) {
    return obj.map(item => resolveReferences(item, definitions, visited));
  }

  // Handle $ref
  if (obj.$ref) {
    const refPath = obj.$ref;
    
    // Prevent circular references
    if (visited.has(refPath)) {
      console.warn(`Circular reference detected: ${refPath}`);
      return { type: 'object' }; // Fallback for circular refs
    }
    
    // Parse the reference (e.g., "#/$defs/CreateCourseArgs")
    const refParts = refPath.split('/');
    const refKey = refParts[refParts.length - 1];
    
    // Look up the definition
    if (definitions[refKey]) {
      visited.add(refPath);
      const resolved = resolveReferences(definitions[refKey], definitions, new Set(visited));
      visited.delete(refPath);
      return resolved;
    } else {
      console.warn(`Reference not found: ${refPath}`);
      return { type: 'object' }; // Fallback
    }
  }

  // Recursively process object properties
  const result: any = {};
  for (const [key, value] of Object.entries(obj)) {
    if (key === '$defs' || key === 'definitions') {
      // Skip definitions - they'll be inlined where referenced
      continue;
    }
    result[key] = resolveReferences(value, definitions, visited);
  }

  return result;
}

/**
 * Flatten tool schemas for use with AI providers
 * Transforms MCP tool format to be compatible with providers that don't support $ref
 * 
 * @param tools - Array of MCP tools
 * @returns Array of tools with flattened schemas
 */
export function flattenToolSchemas(tools: any[]): any[] {
  return tools.map(tool => ({
    ...tool,
    inputSchema: tool.inputSchema ? flattenSchema(tool.inputSchema) : tool.inputSchema,
    outputSchema: tool.outputSchema ? flattenSchema(tool.outputSchema) : tool.outputSchema,
  }));
}

/**
 * Example usage:
 * 
 * // Original schema with $ref
 * const schema = {
 *   "$defs": {
 *     "CreateCourseArgs": {
 *       "properties": {
 *         "courseCode": { "type": "string" },
 *         "title": { "type": "string" }
 *       },
 *       "required": ["courseCode", "title"]
 *     }
 *   },
 *   "properties": {
 *     "args": { "$ref": "#/$defs/CreateCourseArgs" }
 *   }
 * };
 * 
 * // Flattened schema
 * const flattened = flattenSchema(schema);
 * // Result:
 * // {
 * //   "properties": {
 * //     "args": {
 * //       "properties": {
 * //         "courseCode": { "type": "string" },
 * //         "title": { "type": "string" }
 * //       },
 * //       "required": ["courseCode", "title"]
 * //     }
 * //   }
 * // }
 */
