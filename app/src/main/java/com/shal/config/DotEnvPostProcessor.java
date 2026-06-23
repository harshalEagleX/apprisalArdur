package com.shal.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertiesPropertySource;

import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Properties;

/**
 * Loads .env from the project root regardless of working directory.
 *
 * spring.config.import=optional:file:.env[.properties] only works when CWD == the directory
 * containing .env. When IntelliJ or Maven runs the app from the module directory (app/) instead
 * of the project root, it silently skips the file and every INTERNAL_API_KEY reference fails
 * resolution before the Java app can call the Python service.
 *
 * This processor walks up from CWD until it finds .env (max 5 levels), then adds it as a
 * low-priority property source. System env vars and application.yml always win over these values.
 */
public class DotEnvPostProcessor implements EnvironmentPostProcessor, Ordered {

    private static final Logger log = LoggerFactory.getLogger(DotEnvPostProcessor.class);
    private static final String SOURCE_NAME = "shal-dotenv";

    @Override
    public int getOrder() {
        return Ordered.LOWEST_PRECEDENCE - 5;
    }

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        if (environment.getPropertySources().contains(SOURCE_NAME)) {
            return;
        }

        Path dotEnv = findDotEnv();
        if (dotEnv == null) {
            log.debug("DotEnvPostProcessor: no .env found within 5 parent directories of CWD={}",
                    Paths.get("").toAbsolutePath());
            return;
        }

        Properties props = loadProperties(dotEnv);
        if (props.isEmpty()) {
            return;
        }

        // addLast = lowest priority. System env vars (exported INTERNAL_API_KEY etc.) and
        // application.yml explicit values both override what comes from .env.
        environment.getPropertySources().addLast(new PropertiesPropertySource(SOURCE_NAME, props));
        log.info("DotEnvPostProcessor: loaded {} propert{} from {}",
                props.size(), props.size() == 1 ? "y" : "ies", dotEnv);
    }

    private Path findDotEnv() {
        Path dir = Paths.get("").toAbsolutePath();
        for (int depth = 0; depth < 5; depth++) {
            Path candidate = dir.resolve(".env");
            if (Files.isRegularFile(candidate)) {
                return candidate;
            }
            Path parent = dir.getParent();
            if (parent == null) break;
            dir = parent;
        }
        return null;
    }

    private Properties loadProperties(Path path) {
        Properties props = new Properties();
        try (Reader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            props.load(reader);
        } catch (IOException e) {
            log.warn("DotEnvPostProcessor: could not read {}: {}", path, e.getMessage());
        }
        return props;
    }
}
