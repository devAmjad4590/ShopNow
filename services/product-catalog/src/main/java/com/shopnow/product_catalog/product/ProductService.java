package com.shopnow.product_catalog.product;

import com.shopnow.product_catalog.category.Category;
import com.shopnow.product_catalog.category.CategoryService;
import com.shopnow.product_catalog.event.ProductCreatedEvent;
import com.shopnow.product_catalog.exception.ResourceNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class ProductService {

    private static final String PRODUCT_EVENTS = "product-events";

    private final ProductRepository productRepository;
    private final CategoryService categoryService;
    private final KafkaTemplate<String, Object> kafkaTemplate;

    public Page<ProductResponse> getAll(Integer categoryId, Pageable pageable) {
        Page<Product> page = categoryId != null
                ? productRepository.findByCategoryId(categoryId, pageable)
                : productRepository.findAll(pageable);
        return page.map(this::toResponse);
    }

    public ProductResponse getById(Integer id) {
        return toResponse(findOrThrow(id));
    }

    public ProductResponse create(ProductRequest request) {
        categoryService.findOrThrow(request.categoryId());
        Product product = Product.builder()
                .name(request.name())
                .description(request.description())
                .price(request.price())
                .imageUrl(request.imageUrl())
                .categoryId(request.categoryId())
                .stock(request.stock() != null ? request.stock() : 0)
                .build();
        Product saved = productRepository.save(product);
        kafkaTemplate.send(PRODUCT_EVENTS, new ProductCreatedEvent(
                "PRODUCT_CREATED",
                saved.getId().longValue(),
                saved.getName(),
                saved.getStock()
        ));
        return toResponse(saved);
    }

    public ProductResponse update(Integer id, ProductRequest request) {
        Product product = findOrThrow(id);
        categoryService.findOrThrow(request.categoryId());
        product.setName(request.name());
        product.setDescription(request.description());
        product.setPrice(request.price());
        product.setImageUrl(request.imageUrl());
        product.setCategoryId(request.categoryId());
        product.setStock(request.stock() != null ? request.stock() : 0);
        return toResponse(productRepository.save(product));
    }

    public void delete(Integer id) {
        findOrThrow(id);
        productRepository.deleteById(id);
    }

    Product findOrThrow(Integer id) {
        return productRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Product not found: " + id));
    }

    private ProductResponse toResponse(Product p) {
        Category category = categoryService.findOrThrow(p.getCategoryId());
        return new ProductResponse(
                p.getId(), p.getName(), p.getDescription(),
                p.getPrice(), p.getImageUrl(),
                p.getCategoryId(), category.getName(),
                p.getStock(), p.getCreatedAt(), p.getUpdatedAt()
        );
    }
}
