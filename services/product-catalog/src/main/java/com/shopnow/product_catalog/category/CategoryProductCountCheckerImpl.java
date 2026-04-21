package com.shopnow.product_catalog.category;

import com.shopnow.product_catalog.product.ProductRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class CategoryProductCountCheckerImpl implements CategoryProductCountChecker {

    private final ProductRepository productRepository;

    @Override
    public long countByCategoryId(Integer categoryId) {
        return productRepository.countByCategoryId(categoryId);
    }
}
