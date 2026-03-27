from django.db import models

class Produto(models.Model):
    LOJAS_CHOICES = [
        ('ML', 'Mercado Livre'),
        ('KB', 'KaBuM'),
        ('TB', 'Terabyte'),
    ]

    nome = models.CharField(max_length=500)
    preco_atual = models.DecimalField(max_digits=10, decimal_places=2)
    preco_original = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    loja = models.CharField(max_length=50, choices=LOJAS_CHOICES)
    link = models.URLField(max_length=1000)
    imagem = models.URLField(max_length=1000, null=True, blank=True)
    score = models.FloatField(default=0.0)
    data_coleta = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nome} - {self.loja}"

    class Meta:
        ordering = ['-data_coleta', '-score']