package com.shopnow.user_service.config;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.server.ResponseStatusException;

public class HeaderArgumentResolver implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(AuthUserId.class)
                || parameter.hasParameterAnnotation(AuthRole.class);
    }

    @Override
    public Object resolveArgument(MethodParameter parameter,
                                  ModelAndViewContainer mavContainer,
                                  NativeWebRequest webRequest,
                                  WebDataBinderFactory binderFactory) {
        HttpServletRequest request = webRequest.getNativeRequest(HttpServletRequest.class);

        if (parameter.hasParameterAnnotation(AuthUserId.class)) {
            String header = request != null ? request.getHeader("X-User-Id") : null;
            if (header == null) {
                throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Missing X-User-Id header");
            }
            return Integer.parseInt(header);
        }

        if (parameter.hasParameterAnnotation(AuthRole.class)) {
            String header = request != null ? request.getHeader("X-User-Role") : null;
            if (header == null) {
                throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Missing X-User-Role header");
            }
            return header;
        }

        return null;
    }
}
