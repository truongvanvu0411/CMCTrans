# AGENTS.md

## Scope
- This specification applies to **all directories and files in this repository**.
- If a subdirectory contains a new `AGENTS.md`, it may **only add additional rules**, and **must not weaken the strict constraints defined in this file**.

## Project Goals and Coding Principles
- This project is designed as a **brand-new system**, where **consistency** and **simplicity** are the highest priorities.
- Introducing redundant branches, compatibility layers, dual-track logic, or temporary patches for the sake of **“compatibility with legacy code or legacy behavior”** is strictly prohibited.
- New features and refactoring should prioritize **consistency, maintainability, and readability**, rather than accommodating historical baggage.
- The use of the `any` type is **strictly prohibited**. All types **must be explicitly defined**.

## File and Modularization Requirements
- Large files **must be split into clear modules** and organized according to responsibility boundaries.
- If a single file handles **multiple responsibilities** (e.g., UI, state management, data requests, and transformation logic mixed together), it **must be split**.
- Common capabilities should be **extracted into reusable modules** to avoid copy-paste duplication.
- Naming must clearly reflect responsibilities, and the **directory structure should support fast navigation and readability**.

## Data Safety and High-Risk Operations
- Any operation that may cause **data deletion, loss, overwrite, structural changes, or irreversible modifications** must obtain **explicit user consent before execution**.
- Without explicit consent, only **read-only analysis, solution design, and risk explanation** are allowed. Execution is not permitted.
- Scenarios involving **databases, batch file rewrites, migration scripts, cleanup scripts, or overwrite operations** must always be treated as **high-risk operations**.
- However, harmless operations such as **running tests or builds** are allowed.
- Commands that are non-destructive, such as **tests or builds**, may be executed.

## Thinking and Decision-Making Method
- All solutions must follow **first-principles thinking**: clearly define **goals, constraints, and facts**, then derive the implementation path.
- Decisions must **not** be made based solely on **“common practice” or “historical precedent.”** Core assumptions and trade-off reasoning must be clearly stated.
- Implementations should aim for **minimal necessary complexity**, avoiding unnecessary abstractions and over-engineering.

## Command and Git Operation Restrictions
- **No commands may be executed except read-only Git queries.**
- Allowed Git read-only operations include **status and history queries**, such as:
  - `git status`
  - `git log`
  - `git diff`
  - `git show`
  - `git branch` (read-only usage)
- Any operation that **modifies Git state or history** must first obtain **explicit user approval**, including but not limited to:
  - `commit`
  - `push`
  - `pull`
  - `merge`
  - `rebase`
  - `cherry-pick`
  - `reset`
  - `checkout` (modifying usage)
  - creating or deleting branches
  - tagging
- Without approval, **code rewriting, staging, committing, synchronization, rollback, or history rewriting are not allowed**.
- Test-related commands such as **build, lint, and test execution** are allowed.

## Do Not Hide Any Problems
- Do **not introduce unnecessary fallback logic**, especially if it may hide underlying problems.
- Unless explicitly approved by the user, the following behaviors are **forbidden**:
  - Automatically switching to another model when one model becomes unavailable
  - Silently skipping errors when code fails
  - Providing default values when required data is missing
  - Generating fake data
  - Any behavior that masks real issues
- System execution must follow the principle of **explicit failure and zero implicit fallback**:
  - Silent error skipping
  - Implicit configuration fallbacks
  - Automatic model downgrades  
  are strictly prohibited.
- Any unexpected behavior must **fail immediately and report the issue truthfully**.

## Challenge Assumptions and Understand the User’s Real Needs
- Ask questions to understand **what the user truly needs**, not just what they say.
- The user may **not fully understand the code**, and their technical understanding may be **less than yours**.
- Treat user statements as **references rather than absolute truth**.  
  If something does not make sense, **challenge the assumptions**.

## Testing Specification

Detailed specifications can be found in [`agent/testing.md`](agent/testing.md).  
The following are **mandatory core constraints**:

- Any **new feature or modification to existing logic must be tested**.  
  New features must include tests. If code changes require updates to test files, those test files **must be updated accordingly** to ensure tests remain fully aligned.
- Changes to **worker logic / bug fixes / adding routes or task types → tests must be written or updated**.
- Bug fixes must include **new regression tests**, and the `it()` name must clearly reflect the bug scenario.
- Assertions must verify **specific values** (e.g., database field values written, function parameters, return values).  
  Using only `toHaveBeenCalled()` is **not allowed**.
- **Self-fulfilling tests are prohibited**: mocking a return value `X` and then asserting `X` without passing through any real business logic.