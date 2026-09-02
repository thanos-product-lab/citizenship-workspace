"""AI capabilities: the provider boundary, the prompt registry, and the spend ledger.

Architecture RFC §19 and §20. What lives here is narrow by construction — there is
no universal AI function and no agent framework (CLAUDE.md §10). A capability is a
typed input schema, a typed output schema, a versioned prompt, a model config, a
retry limit and a defined failure state, and `service.invoke` is the only way to
reach a provider.

M8 slice 1 builds the boundary and the controls. The capabilities themselves arrive
in slices 2, 3a and 5; the only invocation reachable today is `PROVIDER_PROBE`,
which exists so a deployment can prove its key works.
"""
