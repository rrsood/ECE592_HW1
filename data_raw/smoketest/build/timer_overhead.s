	.file	"timer_overhead.c"
	.text
.Ltext0:
	.file 0 "/home/rrsood/ECE592_HW1" "/home/rrsood/ECE592_HW1/main_code/x86_64/timer_overhead.c"
	.type	tsc_start, @function
tsc_start:
.LFB4373:
	.file 1 "/home/rrsood/ECE592_HW1/main_code/x86_64/timer_overhead.c"
	.loc 1 63 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	movq	%rdi, -24(%rbp)
.LBB12:
.LBB13:
	.file 2 "/usr/lib/gcc/x86_64-redhat-linux/11/include/emmintrin.h"
	.loc 2 1528 3
	lfence
	.loc 2 1529 1
	nop
	movq	-24(%rbp), %rax
	movq	%rax, -16(%rbp)
.LBE13:
.LBE12:
.LBB14:
.LBB15:
	.file 3 "/usr/lib/gcc/x86_64-redhat-linux/11/include/ia32intrin.h"
	.loc 3 124 10
	rdtscp
	movl	%ecx, %esi
	movq	-16(%rbp), %rcx
	movl	%esi, (%rcx)
	salq	$32, %rdx
	orq	%rdx, %rax
.LBE15:
.LBE14:
	.loc 1 66 9
	movq	%rax, -8(%rbp)
.LBB16:
.LBB17:
	.loc 2 1528 3
	lfence
	.loc 2 1529 1
	nop
.LBE17:
.LBE16:
	.loc 1 68 12
	movq	-8(%rbp), %rax
	.loc 1 69 1
	popq	%rbp
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4373:
	.size	tsc_start, .-tsc_start
	.type	tsc_stop, @function
tsc_stop:
.LFB4374:
	.loc 1 72 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	movq	%rdi, -24(%rbp)
	movq	-24(%rbp), %rax
	movq	%rax, -16(%rbp)
.LBB18:
.LBB19:
	.loc 3 124 10
	rdtscp
	movl	%ecx, %esi
	movq	-16(%rbp), %rcx
	movl	%esi, (%rcx)
	salq	$32, %rdx
	orq	%rdx, %rax
.LBE19:
.LBE18:
	.loc 1 74 9
	movq	%rax, -8(%rbp)
.LBB20:
.LBB21:
	.loc 2 1528 3
	lfence
	.loc 2 1529 1
	nop
.LBE21:
.LBE20:
	.loc 1 76 12
	movq	-8(%rbp), %rax
	.loc 1 77 1
	popq	%rbp
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4374:
	.size	tsc_stop, .-tsc_stop
	.section	.rodata
.LC0:
	.string	"usage: %s <num_samples>\n"
	.align 8
.LC1:
	.string	"ERROR: num_samples must be > 0\n"
	.align 8
.LC2:
	.string	"ERROR: malloc failed for %lu samples\n"
	.align 8
.LC3:
	.string	"# cache_bench_metadata_version=1\n"
.LC4:
	.string	"# experiment=timer_overhead\n"
.LC5:
	.string	"# num_samples_requested=%lu\n"
.LC6:
	.string	"# num_samples_emitted=%lu\n"
	.align 8
.LC7:
	.string	"# timer_method=lfence;rdtscp;lfence / rdtscp;lfence\n"
.LC8:
	.string	"# timer_units=TSC_ticks\n"
.LC9:
	.string	"# bracket_contents=empty\n"
	.align 8
.LC10:
	.string	"# logical_cpu_from_tsc_aux=%u\n"
	.align 8
.LC11:
	.string	"# migrated_samples_excluded=%lu\n"
.LC12:
	.string	"sample_index,ticks_elapsed"
.LC13:
	.string	"%lu,%lu\n"
	.text
	.globl	main
	.type	main, @function
main:
.LFB4375:
	.loc 1 80 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	subq	$112, %rsp
	movl	%edi, -100(%rbp)
	movq	%rsi, -112(%rbp)
	.loc 1 81 8
	cmpl	$1, -100(%rbp)
	jg	.L8
	.loc 1 82 9
	movq	-112(%rbp), %rax
	movq	(%rax), %rdx
	movq	stderr(%rip), %rax
	movl	$.LC0, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 83 16
	movl	$1, %eax
	jmp	.L9
.L8:
	.loc 1 86 41
	movq	-112(%rbp), %rax
	addq	$8, %rax
	.loc 1 86 28
	movq	(%rax), %rax
	movl	$10, %edx
	movl	$0, %esi
	movq	%rax, %rdi
	call	strtoull
	movq	%rax, -48(%rbp)
	.loc 1 87 8
	cmpq	$0, -48(%rbp)
	jne	.L10
	.loc 1 88 9
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$31, %edx
	movl	$1, %esi
	movl	$.LC1, %edi
	call	fwrite
	.loc 1 89 16
	movl	$1, %eax
	jmp	.L9
.L10:
	.loc 1 92 25
	movq	-48(%rbp), %rax
	salq	$3, %rax
	movq	%rax, %rdi
	call	malloc
	movq	%rax, -56(%rbp)
	.loc 1 93 8
	cmpq	$0, -56(%rbp)
	jne	.L11
	.loc 1 94 9
	movq	stderr(%rip), %rax
	movq	-48(%rbp), %rdx
	movl	$.LC2, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 96 16
	movl	$1, %eax
	jmp	.L9
.L11:
.LBB22:
	.loc 1 103 19
	movq	$0, -8(%rbp)
	.loc 1 103 5
	jmp	.L12
.L13:
.LBB23:
	.loc 1 105 15 discriminator 3
	leaq	-76(%rbp), %rax
	movq	%rax, %rdi
	call	tsc_start
	.loc 1 106 15 discriminator 3
	leaq	-80(%rbp), %rax
	movq	%rax, %rdi
	call	tsc_stop
.LBE23:
	.loc 1 103 37 discriminator 3
	addq	$1, -8(%rbp)
.L12:
	.loc 1 103 28 discriminator 1
	cmpq	$999, -8(%rbp)
	jbe	.L13
.LBE22:
	.loc 1 109 14
	movl	$0, -12(%rbp)
	.loc 1 110 14
	movq	$0, -24(%rbp)
.LBB24:
	.loc 1 112 19
	movq	$0, -32(%rbp)
	.loc 1 112 5
	jmp	.L14
.L18:
.LBB25:
	.loc 1 118 23
	leaq	-84(%rbp), %rax
	movq	%rax, %rdi
	call	tsc_start
	movq	%rax, -64(%rbp)
	.loc 1 119 23
	leaq	-88(%rbp), %rax
	movq	%rax, %rdi
	call	tsc_stop
	movq	%rax, -72(%rbp)
	.loc 1 121 12
	cmpq	$0, -32(%rbp)
	jne	.L15
	.loc 1 121 31 discriminator 1
	movl	-84(%rbp), %eax
	movl	%eax, -12(%rbp)
.L15:
	.loc 1 123 19
	movl	-84(%rbp), %edx
	movl	-88(%rbp), %eax
	.loc 1 123 12
	cmpl	%eax, %edx
	je	.L16
	.loc 1 124 20
	movq	-32(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 124 24
	movq	$-1, (%rax)
	.loc 1 125 29
	addq	$1, -24(%rbp)
	jmp	.L17
.L16:
	.loc 1 127 20
	movq	-32(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rax, %rdx
	.loc 1 127 29
	movq	-72(%rbp), %rax
	subq	-64(%rbp), %rax
	.loc 1 127 24
	movq	%rax, (%rdx)
.L17:
.LBE25:
	.loc 1 112 44 discriminator 2
	addq	$1, -32(%rbp)
.L14:
	.loc 1 112 28 discriminator 1
	movq	-32(%rbp), %rax
	cmpq	-48(%rbp), %rax
	jb	.L18
.LBE24:
	.loc 1 131 5
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$33, %edx
	movl	$1, %esi
	movl	$.LC3, %edi
	call	fwrite
	.loc 1 132 5
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$28, %edx
	movl	$1, %esi
	movl	$.LC4, %edi
	call	fwrite
	.loc 1 133 5
	movq	stderr(%rip), %rax
	movq	-48(%rbp), %rdx
	movl	$.LC5, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 134 5
	movq	-48(%rbp), %rax
	subq	-24(%rbp), %rax
	movq	%rax, %rdx
	movq	stderr(%rip), %rax
	movl	$.LC6, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 136 5
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$52, %edx
	movl	$1, %esi
	movl	$.LC7, %edi
	call	fwrite
	.loc 1 137 5
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$24, %edx
	movl	$1, %esi
	movl	$.LC8, %edi
	call	fwrite
	.loc 1 138 5
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$25, %edx
	movl	$1, %esi
	movl	$.LC9, %edi
	call	fwrite
	.loc 1 139 5
	movq	stderr(%rip), %rax
	movl	-12(%rbp), %edx
	movl	$.LC10, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 140 5
	movq	stderr(%rip), %rax
	movq	-24(%rbp), %rdx
	movl	$.LC11, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 143 5
	movl	$.LC12, %edi
	call	puts
.LBB26:
	.loc 1 144 19
	movq	$0, -40(%rbp)
	.loc 1 144 5
	jmp	.L19
.L22:
	.loc 1 145 20
	movq	-40(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rdx, %rax
	movq	(%rax), %rax
	.loc 1 145 12
	cmpq	$-1, %rax
	je	.L23
	.loc 1 146 55
	movq	-40(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 146 9
	movq	(%rax), %rdx
	movq	-40(%rbp), %rax
	movq	%rax, %rsi
	movl	$.LC13, %edi
	movl	$0, %eax
	call	printf
	jmp	.L21
.L23:
	.loc 1 145 44
	nop
.L21:
	.loc 1 144 44 discriminator 2
	addq	$1, -40(%rbp)
.L19:
	.loc 1 144 28 discriminator 1
	movq	-40(%rbp), %rax
	cmpq	-48(%rbp), %rax
	jb	.L22
.LBE26:
	.loc 1 149 5
	movq	-56(%rbp), %rax
	movq	%rax, %rdi
	call	free
	.loc 1 150 12
	movl	$0, %eax
.L9:
	.loc 1 151 1
	leave
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4375:
	.size	main, .-main
.Letext0:
	.file 4 "/usr/lib/gcc/x86_64-redhat-linux/11/include/stddef.h"
	.file 5 "/usr/include/bits/types.h"
	.file 6 "/usr/include/bits/types/struct_FILE.h"
	.file 7 "/usr/include/bits/types/FILE.h"
	.file 8 "/usr/include/bits/stdint-uintn.h"
	.file 9 "/usr/include/stdio.h"
	.file 10 "/usr/include/stdlib.h"
	.section	.debug_info,"",@progbits
.Ldebug_info0:
	.long	0x5c4
	.value	0x5
	.byte	0x1
	.byte	0x8
	.long	.Ldebug_abbrev0
	.uleb128 0x15
	.long	.LASF69
	.byte	0x1d
	.long	.LASF0
	.long	.LASF1
	.quad	.Ltext0
	.quad	.Letext0-.Ltext0
	.long	.Ldebug_line0
	.uleb128 0x6
	.long	.LASF9
	.byte	0x4
	.byte	0xd1
	.byte	0x17
	.long	0x3a
	.uleb128 0x2
	.byte	0x8
	.byte	0x7
	.long	.LASF2
	.uleb128 0x2
	.byte	0x4
	.byte	0x7
	.long	.LASF3
	.uleb128 0x16
	.byte	0x8
	.uleb128 0x2
	.byte	0x1
	.byte	0x8
	.long	.LASF4
	.uleb128 0x2
	.byte	0x2
	.byte	0x7
	.long	.LASF5
	.uleb128 0x2
	.byte	0x1
	.byte	0x6
	.long	.LASF6
	.uleb128 0x2
	.byte	0x2
	.byte	0x5
	.long	.LASF7
	.uleb128 0x17
	.byte	0x4
	.byte	0x5
	.string	"int"
	.uleb128 0x2
	.byte	0x8
	.byte	0x5
	.long	.LASF8
	.uleb128 0x6
	.long	.LASF10
	.byte	0x5
	.byte	0x2d
	.byte	0x1b
	.long	0x3a
	.uleb128 0x6
	.long	.LASF11
	.byte	0x5
	.byte	0x98
	.byte	0x19
	.long	0x6d
	.uleb128 0x6
	.long	.LASF12
	.byte	0x5
	.byte	0x99
	.byte	0x1b
	.long	0x6d
	.uleb128 0x3
	.long	0x9d
	.uleb128 0x2
	.byte	0x1
	.byte	0x6
	.long	.LASF13
	.uleb128 0x18
	.long	0x9d
	.uleb128 0x19
	.long	.LASF70
	.byte	0xd8
	.byte	0x6
	.byte	0x33
	.byte	0x8
	.long	0x213
	.uleb128 0x1
	.long	.LASF14
	.byte	0x35
	.byte	0x7
	.long	0x66
	.byte	0
	.uleb128 0x1
	.long	.LASF15
	.byte	0x38
	.byte	0x9
	.long	0x98
	.byte	0x8
	.uleb128 0x1
	.long	.LASF16
	.byte	0x39
	.byte	0x9
	.long	0x98
	.byte	0x10
	.uleb128 0x1
	.long	.LASF17
	.byte	0x3a
	.byte	0x9
	.long	0x98
	.byte	0x18
	.uleb128 0x1
	.long	.LASF18
	.byte	0x3b
	.byte	0x9
	.long	0x98
	.byte	0x20
	.uleb128 0x1
	.long	.LASF19
	.byte	0x3c
	.byte	0x9
	.long	0x98
	.byte	0x28
	.uleb128 0x1
	.long	.LASF20
	.byte	0x3d
	.byte	0x9
	.long	0x98
	.byte	0x30
	.uleb128 0x1
	.long	.LASF21
	.byte	0x3e
	.byte	0x9
	.long	0x98
	.byte	0x38
	.uleb128 0x1
	.long	.LASF22
	.byte	0x3f
	.byte	0x9
	.long	0x98
	.byte	0x40
	.uleb128 0x1
	.long	.LASF23
	.byte	0x42
	.byte	0x9
	.long	0x98
	.byte	0x48
	.uleb128 0x1
	.long	.LASF24
	.byte	0x43
	.byte	0x9
	.long	0x98
	.byte	0x50
	.uleb128 0x1
	.long	.LASF25
	.byte	0x44
	.byte	0x9
	.long	0x98
	.byte	0x58
	.uleb128 0x1
	.long	.LASF26
	.byte	0x46
	.byte	0x16
	.long	0x22c
	.byte	0x60
	.uleb128 0x1
	.long	.LASF27
	.byte	0x48
	.byte	0x14
	.long	0x231
	.byte	0x68
	.uleb128 0x1
	.long	.LASF28
	.byte	0x4a
	.byte	0x7
	.long	0x66
	.byte	0x70
	.uleb128 0x1
	.long	.LASF29
	.byte	0x51
	.byte	0x7
	.long	0x66
	.byte	0x74
	.uleb128 0x1
	.long	.LASF30
	.byte	0x53
	.byte	0xb
	.long	0x80
	.byte	0x78
	.uleb128 0x1
	.long	.LASF31
	.byte	0x56
	.byte	0x12
	.long	0x51
	.byte	0x80
	.uleb128 0x1
	.long	.LASF32
	.byte	0x57
	.byte	0xf
	.long	0x58
	.byte	0x82
	.uleb128 0x1
	.long	.LASF33
	.byte	0x58
	.byte	0x8
	.long	0x236
	.byte	0x83
	.uleb128 0x1
	.long	.LASF34
	.byte	0x5a
	.byte	0xf
	.long	0x246
	.byte	0x88
	.uleb128 0x1
	.long	.LASF35
	.byte	0x62
	.byte	0xd
	.long	0x8c
	.byte	0x90
	.uleb128 0x1
	.long	.LASF36
	.byte	0x64
	.byte	0x17
	.long	0x250
	.byte	0x98
	.uleb128 0x1
	.long	.LASF37
	.byte	0x65
	.byte	0x19
	.long	0x25a
	.byte	0xa0
	.uleb128 0x1
	.long	.LASF38
	.byte	0x66
	.byte	0x14
	.long	0x231
	.byte	0xa8
	.uleb128 0x1
	.long	.LASF39
	.byte	0x67
	.byte	0x9
	.long	0x48
	.byte	0xb0
	.uleb128 0x1
	.long	.LASF40
	.byte	0x68
	.byte	0xa
	.long	0x2e
	.byte	0xb8
	.uleb128 0x1
	.long	.LASF41
	.byte	0x69
	.byte	0x7
	.long	0x66
	.byte	0xc0
	.uleb128 0x1
	.long	.LASF42
	.byte	0x75
	.byte	0x8
	.long	0x25f
	.byte	0xc4
	.byte	0
	.uleb128 0x6
	.long	.LASF43
	.byte	0x7
	.byte	0x7
	.byte	0x19
	.long	0xa9
	.uleb128 0x1a
	.long	.LASF71
	.byte	0x6
	.byte	0x2d
	.byte	0xe
	.uleb128 0x9
	.long	.LASF44
	.uleb128 0x3
	.long	0x227
	.uleb128 0x3
	.long	0xa9
	.uleb128 0xe
	.long	0x9d
	.long	0x246
	.uleb128 0xf
	.long	0x3a
	.byte	0
	.byte	0
	.uleb128 0x3
	.long	0x21f
	.uleb128 0x9
	.long	.LASF45
	.uleb128 0x3
	.long	0x24b
	.uleb128 0x9
	.long	.LASF46
	.uleb128 0x3
	.long	0x255
	.uleb128 0xe
	.long	0x9d
	.long	0x26f
	.uleb128 0xf
	.long	0x3a
	.byte	0x13
	.byte	0
	.uleb128 0x3
	.long	0x213
	.uleb128 0xa
	.long	0x26f
	.uleb128 0x1b
	.long	.LASF72
	.byte	0x9
	.byte	0x8b
	.byte	0xe
	.long	0x26f
	.uleb128 0x2
	.byte	0x8
	.byte	0x5
	.long	.LASF47
	.uleb128 0x6
	.long	.LASF48
	.byte	0x8
	.byte	0x1b
	.byte	0x14
	.long	0x74
	.uleb128 0x2
	.byte	0x10
	.byte	0x4
	.long	.LASF49
	.uleb128 0x2
	.byte	0x8
	.byte	0x7
	.long	.LASF50
	.uleb128 0x2
	.byte	0x4
	.byte	0x4
	.long	.LASF51
	.uleb128 0x2
	.byte	0x8
	.byte	0x4
	.long	.LASF52
	.uleb128 0x1c
	.long	.LASF73
	.byte	0xa
	.value	0x22a
	.byte	0xd
	.long	0x2c7
	.uleb128 0x5
	.long	0x48
	.byte	0
	.uleb128 0xb
	.long	.LASF53
	.byte	0x9
	.value	0x15e
	.byte	0xc
	.long	0x66
	.long	0x2df
	.uleb128 0x5
	.long	0x2df
	.uleb128 0x10
	.byte	0
	.uleb128 0x3
	.long	0xa4
	.uleb128 0xa
	.long	0x2df
	.uleb128 0xb
	.long	.LASF54
	.byte	0xa
	.value	0x21b
	.byte	0xe
	.long	0x48
	.long	0x300
	.uleb128 0x5
	.long	0x2e
	.byte	0
	.uleb128 0x1d
	.long	.LASF55
	.byte	0xa
	.byte	0xcd
	.byte	0x1f
	.long	0x29f
	.long	0x320
	.uleb128 0x5
	.long	0x2e4
	.uleb128 0x5
	.long	0x325
	.uleb128 0x5
	.long	0x66
	.byte	0
	.uleb128 0x3
	.long	0x98
	.uleb128 0xa
	.long	0x320
	.uleb128 0xb
	.long	.LASF56
	.byte	0x9
	.value	0x158
	.byte	0xc
	.long	0x66
	.long	0x347
	.uleb128 0x5
	.long	0x274
	.uleb128 0x5
	.long	0x2e4
	.uleb128 0x10
	.byte	0
	.uleb128 0x1e
	.long	.LASF74
	.byte	0x1
	.byte	0x4f
	.byte	0x5
	.long	0x66
	.quad	.LFB4375
	.quad	.LFE4375-.LFB4375
	.uleb128 0x1
	.byte	0x9c
	.long	0x49b
	.uleb128 0x8
	.long	.LASF57
	.byte	0x4f
	.byte	0xe
	.long	0x66
	.uleb128 0x3
	.byte	0x91
	.sleb128 -116
	.uleb128 0x8
	.long	.LASF58
	.byte	0x4f
	.byte	0x1b
	.long	0x320
	.uleb128 0x3
	.byte	0x91
	.sleb128 -128
	.uleb128 0x7
	.long	.LASF59
	.byte	0x56
	.byte	0xe
	.long	0x28c
	.uleb128 0x2
	.byte	0x91
	.sleb128 -64
	.uleb128 0x7
	.long	.LASF60
	.byte	0x5c
	.byte	0xf
	.long	0x49b
	.uleb128 0x3
	.byte	0x91
	.sleb128 -72
	.uleb128 0x7
	.long	.LASF61
	.byte	0x6d
	.byte	0xe
	.long	0x41
	.uleb128 0x2
	.byte	0x91
	.sleb128 -28
	.uleb128 0x7
	.long	.LASF62
	.byte	0x6e
	.byte	0xe
	.long	0x28c
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0x11
	.quad	.LBB22
	.quad	.LBE22-.LBB22
	.long	0x40e
	.uleb128 0x4
	.string	"i"
	.byte	0x67
	.byte	0x13
	.long	0x28c
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.uleb128 0xc
	.quad	.LBB23
	.quad	.LBE23-.LBB23
	.uleb128 0x4
	.string	"a"
	.byte	0x68
	.byte	0x12
	.long	0x41
	.uleb128 0x3
	.byte	0x91
	.sleb128 -92
	.uleb128 0x4
	.string	"b"
	.byte	0x68
	.byte	0x15
	.long	0x41
	.uleb128 0x3
	.byte	0x91
	.sleb128 -96
	.byte	0
	.byte	0
	.uleb128 0x11
	.quad	.LBB24
	.quad	.LBE24-.LBB24
	.long	0x47c
	.uleb128 0x4
	.string	"r"
	.byte	0x70
	.byte	0x13
	.long	0x28c
	.uleb128 0x2
	.byte	0x91
	.sleb128 -48
	.uleb128 0xc
	.quad	.LBB25
	.quad	.LBE25-.LBB25
	.uleb128 0x7
	.long	.LASF63
	.byte	0x71
	.byte	0x12
	.long	0x41
	.uleb128 0x3
	.byte	0x91
	.sleb128 -100
	.uleb128 0x7
	.long	.LASF64
	.byte	0x71
	.byte	0x19
	.long	0x41
	.uleb128 0x3
	.byte	0x91
	.sleb128 -104
	.uleb128 0x4
	.string	"t0"
	.byte	0x76
	.byte	0x12
	.long	0x28c
	.uleb128 0x3
	.byte	0x91
	.sleb128 -80
	.uleb128 0x4
	.string	"t1"
	.byte	0x77
	.byte	0x12
	.long	0x28c
	.uleb128 0x3
	.byte	0x91
	.sleb128 -88
	.byte	0
	.byte	0
	.uleb128 0xc
	.quad	.LBB26
	.quad	.LBE26-.LBB26
	.uleb128 0x4
	.string	"r"
	.byte	0x90
	.byte	0x13
	.long	0x28c
	.uleb128 0x2
	.byte	0x91
	.sleb128 -56
	.byte	0
	.byte	0
	.uleb128 0x3
	.long	0x28c
	.uleb128 0x12
	.long	.LASF66
	.byte	0x47
	.long	0x28c
	.quad	.LFB4374
	.quad	.LFE4374-.LFB4374
	.uleb128 0x1
	.byte	0x9c
	.long	0x514
	.uleb128 0x8
	.long	.LASF65
	.byte	0x47
	.byte	0x2b
	.long	0x514
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0x4
	.string	"t"
	.byte	0x49
	.byte	0xe
	.long	0x28c
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.uleb128 0x13
	.long	0x5ad
	.quad	.LBB18
	.quad	.LBE18-.LBB18
	.byte	0x4a
	.long	0x4fd
	.uleb128 0x14
	.long	0x5ba
	.uleb128 0x2
	.byte	0x91
	.sleb128 -32
	.byte	0
	.uleb128 0xd
	.long	0x5a3
	.quad	.LBB20
	.quad	.LBE20-.LBB20
	.byte	0x4b
	.byte	0
	.uleb128 0x3
	.long	0x41
	.uleb128 0x12
	.long	.LASF67
	.byte	0x3e
	.long	0x28c
	.quad	.LFB4373
	.quad	.LFE4373-.LFB4373
	.uleb128 0x1
	.byte	0x9c
	.long	0x5a3
	.uleb128 0x8
	.long	.LASF65
	.byte	0x3e
	.byte	0x2c
	.long	0x514
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0x4
	.string	"t"
	.byte	0x40
	.byte	0xe
	.long	0x28c
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.uleb128 0xd
	.long	0x5a3
	.quad	.LBB12
	.quad	.LBE12-.LBB12
	.byte	0x41
	.uleb128 0x13
	.long	0x5ad
	.quad	.LBB14
	.quad	.LBE14-.LBB14
	.byte	0x42
	.long	0x58c
	.uleb128 0x14
	.long	0x5ba
	.uleb128 0x2
	.byte	0x91
	.sleb128 -32
	.byte	0
	.uleb128 0xd
	.long	0x5a3
	.quad	.LBB16
	.quad	.LBE16-.LBB16
	.byte	0x43
	.byte	0
	.uleb128 0x1f
	.long	.LASF75
	.byte	0x2
	.value	0x5f6
	.byte	0x1
	.byte	0x3
	.uleb128 0x20
	.long	.LASF68
	.byte	0x3
	.byte	0x7a
	.byte	0x1
	.long	0x29f
	.byte	0x3
	.uleb128 0x21
	.string	"__A"
	.byte	0x3
	.byte	0x7a
	.byte	0x19
	.long	0x514
	.byte	0
	.byte	0
	.section	.debug_abbrev,"",@progbits
.Ldebug_abbrev0:
	.uleb128 0x1
	.uleb128 0xd
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 6
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x38
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x2
	.uleb128 0x24
	.byte	0
	.uleb128 0xb
	.uleb128 0xb
	.uleb128 0x3e
	.uleb128 0xb
	.uleb128 0x3
	.uleb128 0xe
	.byte	0
	.byte	0
	.uleb128 0x3
	.uleb128 0xf
	.byte	0
	.uleb128 0xb
	.uleb128 0x21
	.sleb128 8
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x4
	.uleb128 0x34
	.byte	0
	.uleb128 0x3
	.uleb128 0x8
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x5
	.uleb128 0x5
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x6
	.uleb128 0x16
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x7
	.uleb128 0x34
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x8
	.uleb128 0x5
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x9
	.uleb128 0x13
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3c
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0xa
	.uleb128 0x37
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0xb
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x3c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0xc
	.uleb128 0xb
	.byte	0x1
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.byte	0
	.byte	0
	.uleb128 0xd
	.uleb128 0x1d
	.byte	0
	.uleb128 0x31
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x58
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x59
	.uleb128 0xb
	.uleb128 0x57
	.uleb128 0x21
	.sleb128 5
	.byte	0
	.byte	0
	.uleb128 0xe
	.uleb128 0x1
	.byte	0x1
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0xf
	.uleb128 0x21
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2f
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x10
	.uleb128 0x18
	.byte	0
	.byte	0
	.byte	0
	.uleb128 0x11
	.uleb128 0xb
	.byte	0x1
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x12
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0x21
	.sleb128 24
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x40
	.uleb128 0x18
	.uleb128 0x7a
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x13
	.uleb128 0x1d
	.byte	0x1
	.uleb128 0x31
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x58
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x59
	.uleb128 0xb
	.uleb128 0x57
	.uleb128 0x21
	.sleb128 9
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x14
	.uleb128 0x5
	.byte	0
	.uleb128 0x31
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x15
	.uleb128 0x11
	.byte	0x1
	.uleb128 0x25
	.uleb128 0xe
	.uleb128 0x13
	.uleb128 0xb
	.uleb128 0x3
	.uleb128 0x1f
	.uleb128 0x1b
	.uleb128 0x1f
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x10
	.uleb128 0x17
	.byte	0
	.byte	0
	.uleb128 0x16
	.uleb128 0xf
	.byte	0
	.uleb128 0xb
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x17
	.uleb128 0x24
	.byte	0
	.uleb128 0xb
	.uleb128 0xb
	.uleb128 0x3e
	.uleb128 0xb
	.uleb128 0x3
	.uleb128 0x8
	.byte	0
	.byte	0
	.uleb128 0x18
	.uleb128 0x26
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x19
	.uleb128 0x13
	.byte	0x1
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0xb
	.uleb128 0xb
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x1a
	.uleb128 0x16
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x1b
	.uleb128 0x34
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3c
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0x1c
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x3c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x1d
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x3c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x1e
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x40
	.uleb128 0x18
	.uleb128 0x7c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x1f
	.uleb128 0x2e
	.byte	0
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x20
	.uleb128 0xb
	.uleb128 0x34
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0x20
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x20
	.uleb128 0xb
	.uleb128 0x34
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0x21
	.uleb128 0x5
	.byte	0
	.uleb128 0x3
	.uleb128 0x8
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.byte	0
	.section	.debug_aranges,"",@progbits
	.long	0x2c
	.value	0x2
	.long	.Ldebug_info0
	.byte	0x8
	.byte	0
	.value	0
	.value	0
	.quad	.Ltext0
	.quad	.Letext0-.Ltext0
	.quad	0
	.quad	0
	.section	.debug_line,"",@progbits
.Ldebug_line0:
	.section	.debug_str,"MS",@progbits,1
.LASF66:
	.string	"tsc_stop"
.LASF52:
	.string	"double"
.LASF70:
	.string	"_IO_FILE"
.LASF25:
	.string	"_IO_save_end"
.LASF7:
	.string	"short int"
.LASF9:
	.string	"size_t"
.LASF54:
	.string	"malloc"
.LASF35:
	.string	"_offset"
.LASF19:
	.string	"_IO_write_ptr"
.LASF14:
	.string	"_flags"
.LASF21:
	.string	"_IO_buf_base"
.LASF26:
	.string	"_markers"
.LASF16:
	.string	"_IO_read_end"
.LASF39:
	.string	"_freeres_buf"
.LASF63:
	.string	"aux_a"
.LASF64:
	.string	"aux_b"
.LASF73:
	.string	"free"
.LASF31:
	.string	"_cur_column"
.LASF51:
	.string	"float"
.LASF72:
	.string	"stderr"
.LASF47:
	.string	"long long int"
.LASF34:
	.string	"_lock"
.LASF8:
	.string	"long int"
.LASF53:
	.string	"printf"
.LASF65:
	.string	"aux_out"
.LASF60:
	.string	"samples"
.LASF67:
	.string	"tsc_start"
.LASF62:
	.string	"migrated_samples"
.LASF58:
	.string	"argv"
.LASF30:
	.string	"_old_offset"
.LASF49:
	.string	"long double"
.LASF4:
	.string	"unsigned char"
.LASF69:
	.string	"GNU C11 11.5.0 20240719 (Red Hat 11.5.0-14) -mtune=generic -march=x86-64-v2 -g -O0 -std=c11 -fno-omit-frame-pointer"
.LASF57:
	.string	"argc"
.LASF55:
	.string	"strtoull"
.LASF6:
	.string	"signed char"
.LASF48:
	.string	"uint64_t"
.LASF50:
	.string	"long long unsigned int"
.LASF3:
	.string	"unsigned int"
.LASF44:
	.string	"_IO_marker"
.LASF33:
	.string	"_shortbuf"
.LASF18:
	.string	"_IO_write_base"
.LASF42:
	.string	"_unused2"
.LASF15:
	.string	"_IO_read_ptr"
.LASF22:
	.string	"_IO_buf_end"
.LASF75:
	.string	"_mm_lfence"
.LASF13:
	.string	"char"
.LASF74:
	.string	"main"
.LASF37:
	.string	"_wide_data"
.LASF38:
	.string	"_freeres_list"
.LASF40:
	.string	"__pad5"
.LASF10:
	.string	"__uint64_t"
.LASF61:
	.string	"aux_first"
.LASF5:
	.string	"short unsigned int"
.LASF2:
	.string	"long unsigned int"
.LASF20:
	.string	"_IO_write_end"
.LASF12:
	.string	"__off64_t"
.LASF68:
	.string	"__rdtscp"
.LASF28:
	.string	"_fileno"
.LASF27:
	.string	"_chain"
.LASF46:
	.string	"_IO_wide_data"
.LASF41:
	.string	"_mode"
.LASF11:
	.string	"__off_t"
.LASF24:
	.string	"_IO_backup_base"
.LASF29:
	.string	"_flags2"
.LASF45:
	.string	"_IO_codecvt"
.LASF17:
	.string	"_IO_read_base"
.LASF32:
	.string	"_vtable_offset"
.LASF36:
	.string	"_codecvt"
.LASF23:
	.string	"_IO_save_base"
.LASF43:
	.string	"FILE"
.LASF56:
	.string	"fprintf"
.LASF59:
	.string	"num_samples"
.LASF71:
	.string	"_IO_lock_t"
	.section	.debug_line_str,"MS",@progbits,1
.LASF1:
	.string	"/home/rrsood/ECE592_HW1"
.LASF0:
	.string	"/home/rrsood/ECE592_HW1/main_code/x86_64/timer_overhead.c"
	.ident	"GCC: (GNU) 11.5.0 20240719 (Red Hat 11.5.0-14)"
	.section	.note.GNU-stack,"",@progbits
