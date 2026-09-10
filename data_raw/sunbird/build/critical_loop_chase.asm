0000000000401520 <chase>:
  401520:	55                   	push   rbp
  401521:	48 89 e5             	mov    rbp,rsp
  401524:	48 89 7d e8          	mov    QWORD PTR [rbp-0x18],rdi
  401528:	48 89 75 e0          	mov    QWORD PTR [rbp-0x20],rsi
  40152c:	48 c7 45 f8 00 00 00 	mov    QWORD PTR [rbp-0x8],0x0
  401533:	00 
  401534:	eb 10                	jmp    401546 <chase+0x26>
  401536:	48 8b 45 e8          	mov    rax,QWORD PTR [rbp-0x18]
  40153a:	48 8b 00             	mov    rax,QWORD PTR [rax]
  40153d:	48 89 45 e8          	mov    QWORD PTR [rbp-0x18],rax
  401541:	48 83 45 f8 01       	add    QWORD PTR [rbp-0x8],0x1
  401546:	48 8b 45 f8          	mov    rax,QWORD PTR [rbp-0x8]
  40154a:	48 3b 45 e0          	cmp    rax,QWORD PTR [rbp-0x20]
  40154e:	72 e6                	jb     401536 <chase+0x16>
  401550:	48 8b 45 e8          	mov    rax,QWORD PTR [rbp-0x18]
  401554:	5d                   	pop    rbp
  401555:	c3                   	ret    
