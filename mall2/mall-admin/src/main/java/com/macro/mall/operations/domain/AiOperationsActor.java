package com.macro.mall.operations.domain;

import java.util.ArrayList;
import java.util.List;

/** A small authenticated-operator profile; raw role graph is not exposed. */
public class AiOperationsActor {
    private String username;
    private List<String> capabilities = new ArrayList<>();

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }
    public List<String> getCapabilities() { return capabilities; }
    public void setCapabilities(List<String> capabilities) { this.capabilities = capabilities; }
}
