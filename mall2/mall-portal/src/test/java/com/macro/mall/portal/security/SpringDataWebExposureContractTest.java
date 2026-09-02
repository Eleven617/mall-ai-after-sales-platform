package com.macro.mall.portal.security;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The Java 8/Spring Boot 2.7 compatibility line carries a documented,
 * time-bounded Spring Data Commons exception. The affected Spring Data web
 * argument resolvers are not part of the public controller contract: paging
 * and product ordering use bounded integer parameters instead. Keep that
 * property executable so a future controller cannot silently expose
 * user-controlled property paths or projections.
 */
class SpringDataWebExposureContractTest {

    @Test
    void controllersMustNotExposeSpringDataPropertyPathOrProjectionBinding() throws IOException {
        Path mallRoot = findMallRoot();

        assertNoSpringDataWebBinding(mallRoot.resolve("mall-portal/src/main/java"));
        assertNoSpringDataWebBinding(mallRoot.resolve("mall-admin/src/main/java"));
    }

    private void assertNoSpringDataWebBinding(Path sourceRoot) throws IOException {
        try (Stream<Path> paths = Files.walk(sourceRoot)) {
            paths.filter(path -> path.toString().endsWith("Controller.java"))
                    .forEach(path -> assertControllerSourceIsBounded(path));
        }
    }

    private Path findMallRoot() {
        Path current = Paths.get(".").toAbsolutePath().normalize();
        if (Files.isDirectory(current.resolve("mall-portal"))) {
            return current;
        }
        Path parent = current.getParent();
        if (parent != null && Files.isDirectory(parent.resolve("mall-portal"))) {
            return parent;
        }
        throw new IllegalStateException("Cannot locate the Maven reactor root from " + current);
    }

    private void assertControllerSourceIsBounded(Path path) {
        try {
            String source = new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
            assertThat(source)
                    .as("controller source: %s", path)
                    .doesNotContain("org.springframework.data.domain.Pageable")
                    .doesNotContain("org.springframework.data.domain.Sort")
                    .doesNotContain("@ProjectedPayload")
                    .doesNotContain("ProjectionFactory");
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot inspect controller source: " + path, exception);
        }
    }
}
