package com.apprisal;

import org.springframework.boot.SpringApplication;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableScheduling
public class ApprisalApplication {

	public static void main(String[] args) {
		SpringApplication.run(ApprisalApplication.class, args);
	}

}
