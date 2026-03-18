# Development Principles & Best Practices

This document outlines the core architectural principles and best practices to follow when adding new features or updating the WhatsApp AutoGen Bot system. These principles ensure the system remains flexible, stable, reliable, and easy to maintain.

---

## Core Architectural Principles

### 1. **Dependency Injection (DI)**

**Rule**: Never instantiate dependencies directly inside a class. Always receive them through the constructor.

**✅ Good**:
```javascript
class MessageHandlerService {
    constructor(container) {
        this.llmProvider = container.resolve('ILLMProvider');
        this.database = container.resolve('IDatabase');
    }
}
```

**❌ Bad**:
```javascript
class MessageHandlerService {
    constructor() {
        this.llmProvider = new AzureOpenAIAdapter(); // Hard-coded dependency
        this.database = new SQLiteAdapter(); // Cannot swap or test
    }
}
```

**Why**: Makes testing easy (mock dependencies), enables swapping implementations, and reduces coupling.

---

### 2. **Interface Abstraction**

**Rule**: Always code against interfaces, never concrete implementations.

**✅ Good**:
```javascript
// Service depends on interface
class MediaHandlerService {
    constructor(container) {
        this.mediaProcessor = container.resolve('IMediaProcessor'); // Interface
    }
}

// Factory decides implementation
container.singleton('IMediaProcessor', () => {
    return new AzureMediaAdapter(); // Can swap to GoogleMediaAdapter
});
```

**❌ Bad**:
```javascript
class MediaHandlerService {
    constructor() {
        this.mediaProcessor = new AzureMediaAdapter(); // Concrete class
    }
}
```

**Why**: Enables switching providers (Azure → Google → Local) by changing one line in `Application.js`.

---

### 3. **Single Responsibility Principle (SRP)**

**Rule**: Each class should have ONE clear responsibility. If you need "and" to describe what a class does, it's doing too much.

**✅ Good**:
- `MediaHandlerService` → Downloads and processes media
- `MessageHandlerService` → Routes messages to correct handler
- `DocumentExtractor` → Extracts text from documents

**❌ Bad**:
```javascript
class MessageService {
    // Handles messages AND processes media AND manages database AND sends notifications
}
```

**Why**: Changes to one feature don't break others. Easier to test and understand.

---

### 4. **Adapter Pattern**

**Rule**: Wrap all external services (APIs, libraries, databases) in adapter classes that implement your interfaces.

**Structure**:
```
External Service (Azure OpenAI, WhatsApp, SQLite)
         ↓
    Adapter (AzureOpenAIAdapter, WhatsAppAdapter, SQLiteAdapter)
         ↓
    Interface (ILLMProvider, IMessageProvider, IDatabase)
         ↓
    Your Services (MessageHandlerService, etc.)
```

**Why**: If Azure changes their API, you only update `AzureOpenAIAdapter`. The rest of your system is untouched.

---

### 5. **Configuration Over Code**

**Rule**: Use environment variables and config files for behavior changes. Never hard-code values.

**✅ Good**:
```javascript
const maxTokens = this.config.get('llm.maxTokens', 4096);
const enableMedia = process.env.ENABLE_MEDIA_PROCESSING === 'true';
```

**❌ Bad**:
```javascript
const maxTokens = 4096; // Hard-coded
if (true) { // Feature always on
```

**Why**: Turn features on/off, change limits, or switch providers without redeploying code.

---

### 6. **Graceful Degradation**

**Rule**: Optional features should fail gracefully without crashing the entire system.

**✅ Good**:
```javascript
// In Application.js
const optionalServices = ['PythonBridge', 'MediaHandlerService'];

for (const serviceName of services) {
    try {
        await service.start();
    } catch (error) {
        if (optionalServices.includes(serviceName)) {
            logger.warn(`Optional service ${serviceName} failed (will use fallback)`);
        } else {
            throw error; // Critical service failure
        }
    }
}
```

**❌ Bad**:
```javascript
await pythonBridge.start(); // Crashes entire app if Python not installed
```

**Why**: System continues working even if optional dependencies are missing.

---

### 7. **Factory Pattern for Service Creation**

**Rule**: Use factories to create services based on configuration. Never use `new` directly in business logic.

**✅ Good**:
```javascript
// In Application.js
this.container.singleton('ILLMProvider', (container) => {
    const config = container.resolve('ConfigurationManager');
    switch (config.get('llm.provider')) {
        case 'claude': return new ClaudeAdapter();
        case 'gemini': return new GeminiAdapter();
        default: return new AzureOpenAIAdapter();
    }
});
```

**❌ Bad**:
```javascript
const llm = new AzureOpenAIAdapter(); // Hard-coded in service
```

**Why**: Switch providers by changing config, not code.

---

### 8. **Separation of Concerns (Layered Architecture)**

**Rule**: Keep layers separate. Each layer should only know about the layer directly below it.

**Layers**:
```
┌─────────────────────────────────────┐
│  Application Layer                  │  ← Bootstrap, DI container
│  (Application.js, ServiceContainer) │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Service Layer                      │  ← Business logic
│  (MessageHandlerService, etc.)      │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Interface Layer                    │  ← Contracts
│  (ILLMProvider, IDatabase, etc.)    │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  Adapter Layer                      │  ← External integrations
│  (AzureOpenAIAdapter, etc.)         │
└─────────────────────────────────────┘
```

**Why**: Changes in one layer don't cascade to others.

---

### 9. **Event-Driven Architecture**

**Rule**: Use events for loose coupling between components.

**✅ Good**:
```javascript
// WhatsAppAdapter emits events
this.client.on('message', (message) => {
    this.eventHandlers.message.forEach(handler => handler(message));
});

// MessageHandlerService subscribes
this.messageProvider.onMessage(this.handleIncomingMessage.bind(this));
```

**❌ Bad**:
```javascript
// Direct coupling
whatsappAdapter.setMessageHandler(messageHandlerService);
```

**Why**: Components don't need to know about each other. Easy to add new subscribers.

---

### 10. **Database Schema Versioning**

**Rule**: Never modify database schema directly. Always use migration scripts.

**✅ Good**:
```sql
-- migrations/003_add_prompts_table.sql
CREATE TABLE IF NOT EXISTS prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_type TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**❌ Bad**:
```javascript
// Modifying schema in code without migration
await db.run('ALTER TABLE users ADD COLUMN new_field TEXT');
```

**Why**: Track schema changes, rollback if needed, and ensure consistency across environments.

---

### 11. **Command/Query Separation (CQRS)**

**Rule**: Separate operations that **read** state from operations that **change** state. Never mix reads and writes in the same handler.

**✅ Good**:
```javascript
// Query — pure read, no side effects
class GetPlanStatusQuery {
    async execute(planId) {
        return await this.planRepository.findById(planId);
    }
}

// Command — changes state
class UpdatePlanStepCommand {
    async execute(planId, stepId, newStatus) {
        await this.planRepository.updateStep(planId, stepId, newStatus);
        this.eventBus.emit('plan:step:updated', { planId, stepId, newStatus });
    }
}
```

**❌ Bad**:
```javascript
class PlanService {
    async getAndUpdatePlan(planId, stepId) {
        const plan = await this.db.get(planId); // Read
        plan.steps[stepId].status = 'done';     // Write
        await this.db.save(plan);               // Write
        return plan;                            // Read
    }
}
```

**Why**: Prevents race conditions in multi-agent systems. Agents querying the plan don't interfere with agents updating it. Makes the system auditable and scalable.

---

### 12. **Message Bus / Internal Event Queue**

**Rule**: All agent-to-agent communication must go through a centralized **message bus** with typed, structured messages. Agents never call each other directly.

**✅ Good**:
```javascript
// Agent publishes a typed message
this.messageBus.publish('agent:research:complete', {
    requestId: '123',
    agentId: 'researcher-01',
    payload: { findings: [...] },
    timestamp: Date.now()
});

// Another agent subscribes
this.messageBus.subscribe('agent:research:complete', async (message) => {
    await this.incorporateFindings(message.payload.findings);
});
```

**❌ Bad**:
```javascript
// Direct coupling between agents
const findings = await researcherAgent.doResearch(query);
plannerAgent.updatePlan(findings);
```

**Why**: Agents remain decoupled. New agents can subscribe to existing message types without modifying existing code. Enables replay, debugging, and audit trails.

---

### 13. **Idempotent Operations**

**Rule**: Every agent action must be **idempotent** — executing it twice with the same input produces the same result with no unintended side effects.

**✅ Good**:
```javascript
class EmailSkill {
    async execute(params) {
        const idempotencyKey = this.generateKey(params);
        const existing = await this.actionLog.find(idempotencyKey);
        if (existing) {
            return existing.result; // Already done, return cached result
        }
        const result = await this.emailProvider.send(params);
        await this.actionLog.record(idempotencyKey, result);
        return result;
    }
}
```

**❌ Bad**:
```javascript
class EmailSkill {
    async execute(params) {
        await this.emailProvider.send(params); // Sends duplicate if retried
    }
}
```

**Why**: Critical for retry logic, fault tolerance, and crash recovery. If an agent crashes mid-task and restarts, it won't duplicate work.

---

### 14. **Capability-Based Security (Agent Sandboxing)**

**Rule**: Each agent must have an explicit **capability manifest** defining what it is allowed to do. The orchestrator enforces these boundaries.

**✅ Good**:
```javascript
// Agent capability manifest
const coderAgentCapabilities = {
    agentId: 'coder-01',
    allowed: ['file:read', 'file:write', 'command:execute'],
    denied: ['email:send', 'web:search', 'payment:process'],
    resourceLimits: {
        maxFileSize: '10MB',
        maxExecutionTime: 30000, // 30 seconds
        allowedDirectories: ['/workspace/project/**']
    }
};

// Orchestrator enforces before execution
class CapabilityGuard {
    authorize(agentId, action) {
        const caps = this.registry.get(agentId);
        if (!caps.allowed.includes(action)) {
            throw new UnauthorizedAgentAction(agentId, action);
        }
    }
}
```

**❌ Bad**:
```javascript
// Any agent can do anything
class Agent {
    async execute(action) {
        return await action.run(); // No permission check
    }
}
```

**Why**: Prevents runaway agents. A research agent can't accidentally delete files. A coder agent can't send emails. Defense in depth.

---

### 15. **Audit Trail / Action Logging**

**Rule**: Every agent decision, tool call, plan update, and inter-agent message must be recorded in a structured **audit trail**. This is not optional logging — it's a first-class system feature.

**✅ Good**:
```javascript
class AuditTrail {
    async record(entry) {
        await this.store.append({
            id: uuid(),
            timestamp: Date.now(),
            agentId: entry.agentId,
            action: entry.action,        // 'tool:call', 'plan:update', 'decision:made'
            input: entry.input,
            output: entry.output,
            reasoning: entry.reasoning,   // Why the agent made this decision
            parentId: entry.parentId,     // Links to parent task/conversation
            metadata: entry.metadata
        });
    }
}

// Every agent action goes through audit
async executeWithAudit(agentId, action, input) {
    const output = await action.execute(input);
    await this.auditTrail.record({ agentId, action: action.name, input, output });
    return output;
}
```

**❌ Bad**:
```javascript
try {
    await action.execute(input);
} catch (e) {
    console.log(e); // Only logging errors, no trace of successful actions
}
```

**Why**: Users can see *why* the system made a decision. Essential for debugging multi-agent interactions, compliance, and trust.

---

### 16. **Retry & Circuit Breaker Pattern**

**Rule**: All external calls (LLM APIs, web search, email services) must have **automatic retry with exponential backoff** and a **circuit breaker** that stops calling a failing service after N consecutive failures.

**✅ Good**:
```javascript
class CircuitBreaker {
    constructor(options) {
        this.failureThreshold = options.failureThreshold || 5;
        this.resetTimeout = options.resetTimeout || 60000;
        this.state = 'CLOSED'; // CLOSED → OPEN → HALF_OPEN
        this.failureCount = 0;
    }

    async execute(fn) {
        if (this.state === 'OPEN') {
            throw new ServiceUnavailableError('Circuit breaker is OPEN');
        }
        try {
            const result = await this.retryWithBackoff(fn, { maxRetries: 3 });
            this.onSuccess();
            return result;
        } catch (error) {
            this.onFailure();
            throw error;
        }
    }
}
```

**❌ Bad**:
```javascript
// No retry, no protection
const response = await fetch(apiUrl); // Fails once = task fails
```

**Why**: External services are unreliable. Retries handle transient failures. Circuit breakers prevent cascading failures when a service is down.

---

### 17. **State Machine for Task Lifecycle**

**Rule**: Every task and plan must follow a strict **state machine**. No skipping states. Transitions must be explicit and validated.

**✅ Good**:
```javascript
const TaskStates = {
    PENDING: 'pending',
    PLANNING: 'planning',
    AWAITING_APPROVAL: 'awaiting_approval',
    IN_PROGRESS: 'in_progress',
    REVIEW: 'review',
    COMPLETED: 'completed',
    FAILED: 'failed',
    CANCELLED: 'cancelled'
};

const VALID_TRANSITIONS = {
    pending: ['planning', 'cancelled'],
    planning: ['awaiting_approval', 'failed'],
    awaiting_approval: ['in_progress', 'planning', 'cancelled'],
    in_progress: ['review', 'failed', 'cancelled'],
    review: ['completed', 'in_progress', 'failed'],
    completed: [],
    failed: ['pending'], // Can retry
    cancelled: []
};

class TaskStateMachine {
    transition(task, newState) {
        const allowed = VALID_TRANSITIONS[task.state];
        if (!allowed.includes(newState)) {
            throw new InvalidTransitionError(task.state, newState);
        }
        task.state = newState;
        this.eventBus.emit('task:transition', { taskId: task.id, from: task.state, to: newState });
    }
}
```

**❌ Bad**:
```javascript
task.status = 'done'; // No validation, can jump from any state to any state
```

**Why**: Makes the system predictable and recoverable. You always know where a task is in its lifecycle. Crash recovery becomes straightforward.

---

### 18. **Plugin Isolation**

**Rule**: Skills and plugins must run in **isolated contexts**. A buggy or slow plugin must never crash or block the orchestrator or other plugins.

**✅ Good**:
```javascript
class PluginSandbox {
    async executePlugin(plugin, params, options = {}) {
        const timeout = options.timeout || 30000;
        const controller = new AbortController();

        const timeoutId = setTimeout(() => controller.abort(), timeout);

        try {
            const result = await Promise.race([
                plugin.execute(params, { signal: controller.signal }),
                this.createTimeoutPromise(timeout)
            ]);
            return { success: true, result };
        } catch (error) {
            return { success: false, error: error.message, pluginId: plugin.id };
        } finally {
            clearTimeout(timeoutId);
        }
    }
}
```

**❌ Bad**:
```javascript
// Plugin runs in main thread with no protection
await plugin.execute(params); // If it hangs, everything hangs
```

**Why**: The orchestrator must remain responsive even if a plugin misbehaves. Resource limits prevent a single plugin from consuming all memory/CPU.

---

### 19. **Schema Validation at Boundaries**

**Rule**: Every message crossing a boundary (agent-to-agent, API request/response, user input, plugin I/O) must be **validated against a schema**. Never trust data crossing a boundary.

**✅ Good**:
```javascript
const AgentMessageSchema = {
    type: 'object',
    required: ['messageId', 'fromAgent', 'toAgent', 'type', 'payload', 'timestamp'],
    properties: {
        messageId: { type: 'string', format: 'uuid' },
        fromAgent: { type: 'string' },
        toAgent: { type: 'string' },
        type: { type: 'string', enum: ['request', 'response', 'broadcast'] },
        payload: { type: 'object' },
        timestamp: { type: 'number' }
    }
};

class MessageBus {
    publish(message) {
        const valid = this.validator.validate(message, AgentMessageSchema);
        if (!valid) {
            throw new InvalidMessageError(this.validator.errors);
        }
        // ... publish
    }
}
```

**❌ Bad**:
```javascript
messageBus.publish({ data: someObject }); // No structure, no validation
```

**Why**: Prevents cascading failures from malformed data. Makes debugging easy — if a message passes validation, you know its structure. Essential for multi-agent reliability.

---

### 20. **Versioned Agent Protocols**

**Rule**: All agent communication protocols must be **versioned**. Agents must declare which protocol versions they support. Breaking changes require a new version.

**✅ Good**:
```javascript
class AgentProtocol {
    static V1 = 'v1';
    static V2 = 'v2';
    static CURRENT = AgentProtocol.V2;
}

class ResearchAgent {
    getSupportedProtocols() {
        return [AgentProtocol.V1, AgentProtocol.V2];
    }

    async handleMessage(message) {
        switch (message.protocolVersion) {
            case 'v1': return this.handleV1(message);
            case 'v2': return this.handleV2(message);
            default: throw new UnsupportedProtocolError(message.protocolVersion);
        }
    }
}
```

**❌ Bad**:
```javascript
// No versioning — changing message format breaks all agents
async handleMessage(message) {
    const data = message.payload; // If payload structure changes, everything breaks
}
```

**Why**: Allows upgrading one agent without breaking others. Enables gradual rollout of protocol changes. Backward compatibility is enforced, not hoped for.

---

## Adding New Features: Step-by-Step Guide

### Example: Adding a New LLM Provider (Google Gemini)

#### Step 1: Create the Adapter
**File**: `nodejs/src/llm/adapters/GeminiAdapter.js`
```javascript
const ILLMProvider = require('../../core/interfaces/ILLMProvider');

class GeminiAdapter extends ILLMProvider {
    constructor(config) {
        super();
        this.apiKey = config.apiKey;
        this.model = config.model || 'gemini-pro';
    }

    async initialize() {
        // Initialize Gemini SDK
    }

    async generateResponse(messages, options) {
        // Call Gemini API
    }

    // Implement all ILLMProvider methods
}

module.exports = GeminiAdapter;
```

#### Step 2: Register in Factory
**File**: `nodejs/src/core/application/Application.js`
```javascript
const GeminiAdapter = require('../../llm/adapters/GeminiAdapter');

// In registerServices()
this.container.singleton('ILLMProvider', (container) => {
    const config = container.resolve('ConfigurationManager');
    switch (config.get('llm.provider')) {
        case 'claude': return new ClaudeAdapter(config.get('llm.claude'));
        case 'gemini': return new GeminiAdapter(config.get('llm.gemini')); // ← Add this
        default: return new AzureOpenAIAdapter(config.get('llm.azureOpenAI'));
    }
});
```

#### Step 3: Add Configuration
**File**: `.env`
```bash
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-pro
```

**File**: `nodejs/config/default.json`
```json
{
  "llm": {
    "provider": "gemini",
    "gemini": {
      "apiKey": "${GEMINI_API_KEY}",
      "model": "${GEMINI_MODEL}"
    }
  }
}
```

#### Step 4: Test
```bash
npm start
# System automatically uses Gemini instead of Azure OpenAI
# Zero changes to MessageHandlerService or any other service
```

---

## Common Patterns for New Features

### Adding a New Service

1. **Create the service class**:
   ```javascript
   class NewService {
       constructor(container) {
           this.dependency = container.resolve('IDependency');
       }
       
       async start() { /* Initialize */ }
       async stop() { /* Cleanup */ }
   }
   ```

2. **Register in DI container** (`Application.js`):
   ```javascript
   this.container.singleton('NewService', NewService);
   ```

3. **Add to startup sequence** (if needed):
   ```javascript
   const services = ['MetricsService', 'NewService', 'MessageHandlerService'];
   ```

### Adding a New Interface

1. **Define the contract**:
   ```javascript
   // src/core/interfaces/INewInterface.js
   class INewInterface {
       async doSomething() {
           throw new Error('doSomething() must be implemented');
       }
   }
   ```

2. **Create an adapter**:
   ```javascript
   // src/adapters/ConcreteAdapter.js
   class ConcreteAdapter extends INewInterface {
       async doSomething() {
           // Implementation
       }
   }
   ```

3. **Register in factory**:
   ```javascript
   this.container.singleton('INewInterface', () => new ConcreteAdapter());
   ```

### Adding a New Plugin/Skill

1. **Create plugin file** in `nodejs/src/plugins/`:
   ```javascript
   class MyPlugin {
       getMetadata() {
           return {
               name: 'my-plugin',
               version: '1.0.0',
               description: 'Does something useful'
           };
       }

       getSkills() {
           return [{
               name: 'my_skill',
               description: 'Skill description',
               keywords: ['keyword1', 'keyword2'],
               execute: async (params) => { /* Logic */ }
           }];
       }
   }
   ```

2. **Plugin auto-loads** on startup (no registration needed)

---

## Code Review Checklist

Before merging any new feature, verify:

- [ ] **DI**: All dependencies injected via constructor
- [ ] **Interfaces**: Service depends on interface, not concrete class
- [ ] **SRP**: Class has one clear responsibility
- [ ] **Config**: No hard-coded values (use `.env` or `config/`)
- [ ] **Error Handling**: Graceful degradation for optional features
- [ ] **Logging**: Appropriate log levels (info, warn, error)
- [ ] **Testing**: Can mock dependencies easily
- [ ] **Documentation**: Update this file if adding new patterns
- [ ] **Migration**: Database changes use migration scripts
- [ ] **Backward Compatibility**: Existing features still work

---

## Anti-Patterns to Avoid

### ❌ God Objects
```javascript
class EverythingService {
    // 5000 lines of code doing everything
}
```
**Fix**: Split into focused services with single responsibilities.

### ❌ Tight Coupling
```javascript
class ServiceA {
    constructor() {
        this.serviceB = new ServiceB(); // Direct dependency
    }
}
```
**Fix**: Use DI and interfaces.

### ❌ Magic Numbers/Strings
```javascript
if (user.role === 'admin') { // Hard-coded string
    await sendMessage('201080929617@c.us', text); // Hard-coded ID
}
```
**Fix**: Use constants or config.

### ❌ Callback Hell
```javascript
doA(() => {
    doB(() => {
        doC(() => {
            // 10 levels deep
        });
    });
});
```
**Fix**: Use async/await.

### ❌ Ignoring Errors
```javascript
try {
    await riskyOperation();
} catch (error) {
    // Silent failure
}
```
**Fix**: Log errors and handle gracefully.

---

## Performance Best Practices

1. **Use connection pooling** for databases
2. **Cache expensive operations** (LLM responses, API calls)
3. **Implement rate limiting** to prevent abuse
4. **Use streaming** for large responses
5. **Lazy load** optional dependencies
6. **Monitor metrics** (response time, error rate, token usage)

---

## Security Best Practices

1. **Never commit secrets** (use `.env` files, add to `.gitignore`)
2. **Validate all inputs** before processing
3. **Sanitize outputs** before sending to users
4. **Use environment variables** for API keys
5. **Implement authentication** for admin endpoints
6. **Rate limit** API calls to prevent DoS
7. **Log security events** (failed auth, suspicious activity)

---

## Testing Strategy

### Unit Tests
- Test individual classes in isolation
- Mock all dependencies
- Focus on business logic

### Integration Tests
- Test service interactions
- Use real database (test instance)
- Verify end-to-end flows

### Example:
```javascript
// Unit test
describe('MessageHandlerService', () => {
    it('should route media messages to MediaHandlerService', async () => {
        const mockMediaHandler = { processMediaMessage: jest.fn() };
        const service = new MessageHandlerService(mockContainer);
        
        await service.handleIncomingMessage(mockMediaMessage);
        
        expect(mockMediaHandler.processMediaMessage).toHaveBeenCalled();
    });
});
```

---

## Deployment Checklist

Before deploying to production:

- [ ] All tests pass
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] Logs reviewed for errors
- [ ] Performance metrics acceptable
- [ ] Rollback plan prepared
- [ ] Documentation updated
- [ ] Feature flags set correctly

---

## Summary

**The Golden Rule**: When adding a new feature, ask yourself:

1. **Can I swap this implementation easily?** → Use interfaces
2. **Can I test this in isolation?** → Use DI
3. **Does this class do one thing well?** → Follow SRP
4. **Can I turn this off without breaking the system?** → Graceful degradation
5. **Will this change affect other parts of the system?** → Minimize coupling

If you follow these principles, your system will remain:
- ✅ **Flexible** (easy to add features)
- ✅ **Stable** (changes don't break existing functionality)
- ✅ **Reliable** (graceful error handling)
- ✅ **Maintainable** (easy to understand and modify)

---

**Last Updated**: February 9, 2026
**Maintainer**: Development Team
