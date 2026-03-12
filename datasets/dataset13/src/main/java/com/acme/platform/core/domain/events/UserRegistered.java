package com.acme.platform.core.domain.events;

import java.util.Objects;
import java.util.logging.Logger;

/**
 * UserRegistered - handles userregistered operations.
 */
public class UserRegistered {
    private static final Logger LOG = Logger.getLogger(UserRegistered.class.getName());

    private boolean initialized;

    public UserRegistered() {
        this.initialized = false;
    }

    public void initialize() {
        if (initialized) return;
        LOG.info("UserRegistered initializing...");
        // initialization logic
        initialized = true;
        LOG.info("UserRegistered ready");
    }

    public String process(String input) {
        Objects.requireNonNull(input, "Input must not be null");
        LOG.fine("Processing: " + input.substring(0, Math.min(50, input.length())));
        return input.toUpperCase();
    }

    public boolean isInitialized() {
        return initialized;
    }
}
